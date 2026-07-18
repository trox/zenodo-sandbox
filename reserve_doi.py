#!/usr/bin/env python3
"""Reserve a Zenodo DOI via the API.

The Zenodo API *does* mint a DOI for you — you do not supply one. When you
create an empty draft deposition, Zenodo automatically pre-reserves a DOI and
returns it under ``metadata.prereserve_doi.doi``.

Two easily-confused metadata fields:

- ``doi``            -> YOU provide an *existing external* DOI (e.g. from a
                        publisher). Leave it empty and Zenodo mints one.
- ``prereserve_doi`` -> Zenodo generates/reserves the DOI for you. Read-only;
                        it cannot be changed and is of the form
                        ``10.5281/zenodo.<recid>``.

The reserved DOI is NOT registered with DataCite (so it won't resolve) until
you publish the deposition, but it is safe to embed in your files/manuscript
beforehand.

Usage:
    export ZENODO_TOKEN=...            # needs the 'deposit:write' scope
    python reserve_doi.py             # against zenodo.org (production)
    python reserve_doi.py --sandbox   # against sandbox.zenodo.org (testing)

Get a token at https://zenodo.org/account/settings/applications/tokens/new/
(or https://sandbox.zenodo.org/... for the sandbox).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def reserve_doi(token: str, base_url: str) -> dict:
    """Create an empty draft deposition; Zenodo pre-reserves a DOI for it."""
    url = f"{base_url}/api/deposit/depositions"
    req = urllib.request.Request(
        url,
        data=b"{}",  # empty deposition -> DOI is auto pre-reserved
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {exc.code} from Zenodo:\n{body}")
    except urllib.error.URLError as exc:
        sys.exit(f"Network error reaching {url}: {exc.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reserve a Zenodo DOI.")
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Use sandbox.zenodo.org instead of production zenodo.org.",
    )
    args = parser.parse_args()

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("Set ZENODO_TOKEN (a personal access token with 'deposit:write').")

    base_url = "https://sandbox.zenodo.org" if args.sandbox else "https://zenodo.org"
    dep = reserve_doi(token, base_url)

    prereserve = dep.get("metadata", {}).get("prereserve_doi", {})
    reserved_doi = prereserve.get("doi")
    recid = prereserve.get("recid")
    deposition_id = dep.get("id")

    print(f"Deposition id : {deposition_id}")
    print(f"Reserved DOI  : {reserved_doi}")
    print(f"Record id     : {recid}")
    print(f"Edit / draft  : {dep.get('links', {}).get('html')}")
    print()
    print("The DOI is reserved but NOT registered until you publish the deposition.")
    print("Next steps: upload files, set metadata (title/creators/etc.), then POST")
    print(f"  {base_url}/api/deposit/depositions/{deposition_id}/actions/publish")


if __name__ == "__main__":
    main()
