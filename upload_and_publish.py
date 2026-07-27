#!/usr/bin/env python3
"""End-to-end Zenodo deposition: reserve DOI -> upload file -> metadata -> publish.

The full lifecycle over the legacy Deposit API:

    1. POST   /api/deposit/depositions            -> create draft (DOI reserved)
    2. PUT    {bucket_url}/{filename}              -> upload file(s)
    3. PUT    /api/deposit/depositions/{id}        -> set metadata
    4. POST   /api/deposit/depositions/{id}/actions/publish  -> publish

Publishing is PERMANENT: the DOI is registered with DataCite and the files can
no longer be changed (you can only create a new version). Test on the sandbox
first.

Usage:
    export ZENODO_TOKEN=...   # token with 'deposit:write' AND 'deposit:actions'
    python upload_and_publish.py path/to/file.csv --sandbox
    python upload_and_publish.py path/to/file.csv --sandbox --publish  # actually publish

Without --publish the script stops after setting metadata and leaves an
unpublished draft you can inspect in the web UI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _request(method: str, url: str, token: str, *, data=None, json_body=None):
    headers = {"Authorization": f"Bearer {token}"}
    body = data
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if not url.lower().startswith("https://"):
        sys.exit(f"Refusing to open non-HTTPS URL: {url}")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:  # nosec B310 - scheme checked above
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {exc.code} {method} {url}\n{detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"Network error {method} {url}: {exc.reason}")


def create_draft(token: str, base: str) -> dict:
    return _request("POST", f"{base}/api/deposit/depositions", token, json_body={})


def upload_file(token: str, bucket_url: str, path: str) -> dict:
    """Upload via the bucket (files) API — the recommended method, handles large files."""
    filename = os.path.basename(path)
    with open(path, "rb") as fh:
        data = fh.read()
    # Note: PUT to {bucket_url}/{filename} streams the raw bytes as the file body.
    return _request("PUT", f"{bucket_url}/{filename}", token, data=data)


def set_metadata(token: str, base: str, dep_id: int, metadata: dict) -> dict:
    url = f"{base}/api/deposit/depositions/{dep_id}"
    return _request("PUT", url, token, json_body={"metadata": metadata})


def publish(token: str, base: str, dep_id: int) -> dict:
    url = f"{base}/api/deposit/depositions/{dep_id}/actions/publish"
    return _request("POST", url, token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a file to Zenodo and (optionally) publish.")
    parser.add_argument("file", help="Path to the file to upload.")
    parser.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org.")
    parser.add_argument("--publish", action="store_true",
                        help="Actually publish (PERMANENT). Omit to leave an unpublished draft.")
    parser.add_argument("--title", default="Sandbox test upload")
    parser.add_argument("--creator", default="Doe, Jane")
    parser.add_argument("--affiliation", default="")
    parser.add_argument("--description", default="Uploaded via the Zenodo API.")
    parser.add_argument("--upload-type", default="dataset",
                        help="dataset | publication | software | poster | image | ...")
    args = parser.parse_args()

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("Set ZENODO_TOKEN (needs 'deposit:write' and 'deposit:actions').")
    if not os.path.isfile(args.file):
        sys.exit(f"No such file: {args.file}")

    base = "https://sandbox.zenodo.org" if args.sandbox else "https://zenodo.org"

    # 1. Create the draft — Zenodo reserves a DOI here.
    dep = create_draft(token, base)
    dep_id = dep["id"]
    bucket_url = dep["links"]["bucket"]
    reserved_doi = dep.get("metadata", {}).get("prereserve_doi", {}).get("doi")
    print(f"[1/4] Draft created: id={dep_id}  reserved DOI={reserved_doi}")

    # 2. Upload the file into the deposition's bucket.
    up = upload_file(token, bucket_url, args.file)
    print(f"[2/4] Uploaded {up.get('key')} ({up.get('size')} bytes, {up.get('checksum')})")

    # 3. Set the minimum required metadata to be publishable.
    creator = {"name": args.creator}
    if args.affiliation:
        creator["affiliation"] = args.affiliation
    metadata = {
        "title": args.title,
        "upload_type": args.upload_type,
        "description": args.description,
        "creators": [creator],
    }
    set_metadata(token, base, dep_id, metadata)
    print(f"[3/4] Metadata set (title={args.title!r}, upload_type={args.upload_type})")

    # 4. Publish — or stop here with a draft you can review in the UI.
    if not args.publish:
        print(f"[4/4] Skipped publish (no --publish). Review the draft at:")
        print(f"      {dep['links'].get('html')}")
        return

    result = publish(token, base, dep_id)
    print(f"[4/4] PUBLISHED. Registered DOI: {result.get('doi')}")
    print(f"      Record: {result.get('links', {}).get('record_html')}")


if __name__ == "__main__":
    main()
