#!/usr/bin/env python3
"""Publish the drafts prepared by batch_reserve.py — the manual, final step.

Reads manifest.csv and publishes every row with status 'draft_ready'. Publishing
is PERMANENT (registers the DOI with DataCite, freezes the files). For that reason
this is deliberately separate from the batch and gated behind --yes.

Recommended review before running:
  - open each record_url in the manifest and check the embedded PDF + metadata
  - or publish a single record first with --only <filename>

Usage
-----
  export ZENODO_TOKEN=...      # needs scopes 'deposit:write' AND 'deposit:actions'
  python publish_from_manifest.py --sandbox --list          # show what would publish
  python publish_from_manifest.py --sandbox --only paper1.pdf --yes
  python publish_from_manifest.py --sandbox --yes           # publish all draft_ready
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

from zenodo_api import PROD, SANDBOX, Zenodo, ZenodoError

FIELDS = [
    "filename", "status", "deposition_id", "reserved_doi",
    "bucket_url", "record_url", "error",
]


def load(path: str) -> "list[dict]":
    if not os.path.exists(path):
        sys.exit(f"No manifest at {path}. Run batch_reserve.py first.")
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save(path: str, rows: "list[dict]") -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish draft_ready records from the manifest.")
    ap.add_argument("--manifest", default="manifest.csv")
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--only", help="Publish just this filename.")
    ap.add_argument("--list", action="store_true", help="List candidates and exit.")
    ap.add_argument("--yes", action="store_true", help="Required to actually publish.")
    args = ap.parse_args()

    rows = load(args.manifest)
    candidates = [r for r in rows if r.get("status") == "draft_ready"]
    if args.only:
        candidates = [r for r in candidates if r["filename"] == args.only]

    if not candidates:
        sys.exit("Nothing with status 'draft_ready' to publish.")

    if args.list or not args.yes:
        print("Would publish:")
        for r in candidates:
            print(f"  {r['filename']:30}  {r['reserved_doi']:24}  {r['record_url']}")
        if not args.yes:
            print("\nRe-run with --yes to publish (PERMANENT).")
        return

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("Set ZENODO_TOKEN (scopes 'deposit:write' and 'deposit:actions').")
    z = Zenodo(token, SANDBOX if args.sandbox else PROD)

    published = failed = 0
    for r in candidates:
        try:
            res = z.publish(int(r["deposition_id"]))
            r["status"] = "published"
            r["record_url"] = res.get("links", {}).get("record_html", r.get("record_url", ""))
            r["error"] = ""
            published += 1
            print(f"[published] {r['filename']} -> {res.get('doi')}")
        except ZenodoError as exc:
            r["error"] = str(exc).splitlines()[0]
            failed += 1
            print(f"[ERROR    ] {r['filename']}: {r['error']}", file=sys.stderr)
        save(args.manifest, rows)

    print(f"\nPublished {published}, failed {failed}.")


if __name__ == "__main__":
    main()
