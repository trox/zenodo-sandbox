#!/usr/bin/env python3
"""Batch: reserve DOI -> embed into PDF -> upload -> set metadata -> STOP at draft.

One PDF == one Zenodo record == one DOI. Publishing is intentionally NOT done
here: the batch leaves reviewable drafts and records everything in a manifest.
Run publish_from_manifest.py afterwards for the final, manual publish step.

Inputs
------
  files.csv    one row per PDF, keyed by `filename`:
               filename,title,description,upload_type,keywords,license,version,publication_date
  authors.csv  long format, joined on `filename`:
               filename,order,name,affiliation,orcid
  <pdf-dir>/   the PDFs, named exactly as `filename` in files.csv

Outputs
-------
  <out-dir>/   copies of each PDF with the DOI embedded (originals untouched)
  manifest.csv source of truth for state; safe to re-run (resumes per file)

Manifest status advances: reserved -> embedded -> uploaded -> described -> draft_ready

Usage
-----
  export ZENODO_TOKEN=...          # needs scope 'deposit:write'
  python batch_reserve.py --sandbox \
      --files files.csv --authors authors.csv \
      --pdf-dir ./pdfs --out-dir ./pdfs_with_doi --stamp

Requires: pypdf (pip install pypdf); reportlab optional for --stamp.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

from embed_doi import embed_doi
from zenodo_api import PROD, SANDBOX, Zenodo, ZenodoError, reserved_doi_of

MANIFEST_FIELDS = [
    "filename", "status", "deposition_id", "reserved_doi",
    "bucket_url", "record_url", "error",
]
# Ordered pipeline; a file resumes at the step after its recorded status.
ORDER = ["", "reserved", "embedded", "uploaded", "described", "draft_ready"]


# -- CSV / manifest I/O -----------------------------------------------------
def read_files_csv(path: str) -> "dict[str, dict]":
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        name = (r.get("filename") or "").strip()
        if not name:
            sys.exit(f"{path}: a row is missing 'filename'")
        if name in out:
            sys.exit(f"{path}: duplicate filename {name!r}")
        out[name] = r
    return out


def read_authors_csv(path: str) -> "dict[str, list]":
    by_file: "dict[str, list]" = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("filename") or "").strip()
            if name:
                by_file[name].append(r)
    for name in by_file:
        by_file[name].sort(key=lambda a: int(a.get("order") or 0))
    return by_file


def load_manifest(path: str) -> "dict[str, dict]":
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["filename"]: r for r in csv.DictReader(fh)}


def write_manifest(path: str, manifest: "dict[str, dict]") -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        for row in manifest.values():
            w.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})
    os.replace(tmp, path)  # atomic: never leave a half-written manifest


def status_lt(a: str, b: str) -> bool:
    return ORDER.index(a or "") < ORDER.index(b)


# -- metadata builder -------------------------------------------------------
def build_metadata(frow: dict, authors: list) -> dict:
    creators = []
    for a in authors:
        c = {"name": (a.get("name") or "").strip()}
        if not c["name"]:
            continue
        if (a.get("affiliation") or "").strip():
            c["affiliation"] = a["affiliation"].strip()
        if (a.get("orcid") or "").strip():
            c["orcid"] = a["orcid"].strip()
        creators.append(c)
    if not creators:
        raise ValueError("no valid authors (need at least one 'name')")

    md = {
        "title": (frow.get("title") or "").strip(),
        "upload_type": (frow.get("upload_type") or "publication").strip(),
        "description": (frow.get("description") or "").strip(),
        "creators": creators,
    }
    if md["upload_type"] == "publication":
        md.setdefault("publication_type", "article")
    if (frow.get("keywords") or "").strip():
        md["keywords"] = [k.strip() for k in frow["keywords"].split(";") if k.strip()]
    if (frow.get("license") or "").strip():
        md["license"] = frow["license"].strip()
    if (frow.get("version") or "").strip():
        md["version"] = frow["version"].strip()
    if (frow.get("publication_date") or "").strip():
        md["publication_date"] = frow["publication_date"].strip()
    for req in ("title", "description"):
        if not md[req]:
            raise ValueError(f"missing required metadata field: {req}")
    return md


# -- main -------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Batch-reserve DOIs and prepare Zenodo drafts.")
    ap.add_argument("--files", default="files.csv")
    ap.add_argument("--authors", default="authors.csv")
    ap.add_argument("--pdf-dir", default="./pdfs")
    ap.add_argument("--out-dir", default="./pdfs_with_doi")
    ap.add_argument("--manifest", default="manifest.csv")
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--stamp", action="store_true", help="Also print the DOI on page 1 (needs reportlab).")
    args = ap.parse_args()

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("Set ZENODO_TOKEN (scope 'deposit:write').")

    files = read_files_csv(args.files)
    authors = read_authors_csv(args.authors)

    # Validate the file<->metadata correspondence up front; fail loudly.
    on_disk = {f for f in os.listdir(args.pdf_dir)} if os.path.isdir(args.pdf_dir) else set()
    missing_on_disk = [f for f in files if f not in on_disk]
    missing_meta = [f for f in on_disk if f.lower().endswith(".pdf") and f not in files]
    if missing_on_disk:
        sys.exit(f"In files.csv but not in {args.pdf_dir}: {missing_on_disk}")
    if missing_meta:
        sys.exit(f"PDF present but no files.csv row: {missing_meta}")

    os.makedirs(args.out_dir, exist_ok=True)
    base = SANDBOX if args.sandbox else PROD
    z = Zenodo(token, base)
    manifest = load_manifest(args.manifest)

    for filename, frow in files.items():
        row = manifest.get(filename, {"filename": filename, "status": ""})
        manifest[filename] = row
        row["error"] = ""
        try:
            # 1. reserve
            if status_lt(row["status"], "reserved"):
                draft = z.create_draft()
                row["deposition_id"] = str(draft["id"])
                row["reserved_doi"] = reserved_doi_of(draft) or ""
                row["bucket_url"] = draft["links"]["bucket"]
                row["record_url"] = draft["links"].get("html", "")
                row["status"] = "reserved"
                write_manifest(args.manifest, manifest)
                print(f"[reserve ] {filename} -> {row['reserved_doi']} (id {row['deposition_id']})")

            out_pdf = os.path.join(args.out_dir, filename)

            # 2. embed the reserved DOI into a copy of the PDF
            if status_lt(row["status"], "embedded"):
                embed_doi(os.path.join(args.pdf_dir, filename), out_pdf,
                          row["reserved_doi"], stamp=args.stamp)
                row["status"] = "embedded"
                write_manifest(args.manifest, manifest)
                print(f"[embed   ] {filename}")

            # 3. upload the embedded PDF
            if status_lt(row["status"], "uploaded"):
                with open(out_pdf, "rb") as fh:
                    z.upload_file(row["bucket_url"], filename, fh.read())
                row["status"] = "uploaded"
                write_manifest(args.manifest, manifest)
                print(f"[upload  ] {filename}")

            # 4. set metadata from the CSVs
            if status_lt(row["status"], "described"):
                md = build_metadata(frow, authors.get(filename, []))
                z.set_metadata(int(row["deposition_id"]), md)
                row["status"] = "described"
                write_manifest(args.manifest, manifest)
                print(f"[describe] {filename}")

            row["status"] = "draft_ready"
            write_manifest(args.manifest, manifest)
        except (ZenodoError, ValueError, OSError) as exc:
            row["error"] = str(exc).splitlines()[0]
            write_manifest(args.manifest, manifest)
            print(f"[ERROR   ] {filename}: {row['error']}", file=sys.stderr)

    ready = sum(1 for r in manifest.values() if r["status"] == "draft_ready")
    failed = sum(1 for r in manifest.values() if r.get("error"))
    print(f"\nDone. {ready} draft(s) ready for review, {failed} with errors.")
    print(f"Review each draft (record_url in {args.manifest}), then run publish_from_manifest.py.")


if __name__ == "__main__":
    main()
