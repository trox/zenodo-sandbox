"""Minimal Zenodo Deposit API client (stdlib only) with ret/backoff on 429/5xx.

Shared by the batch scripts. Covers just the calls the workflow needs:
create draft, upload to bucket, set metadata, publish.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

PROD = "https://zenodo.org"
SANDBOX = "https://sandbox.zenodo.org"


class ZenodoError(RuntimeError):
    def __init__(self, status: int, method: str, url: str, body: str):
        super().__init__(f"HTTP {status} {method} {url}\n{body}")
        self.status = status


class Zenodo:
    def __init__(self, token: str, base_url: str = PROD, *, max_retries: int = 5):
        self.token = token
        self.base = base_url.rstrip("/")
        self.max_retries = max_retries

    # -- low-level ---------------------------------------------------------
    def _request(self, method: str, url: str, *, data=None, json_body=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        body = data
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        # Refuse any non-HTTPS scheme (guards against file:// / custom schemes;
        # see REVIEW.md, addresses bandit B310).
        if not url.lower().startswith("https://"):
            raise ValueError(f"refusing to open non-HTTPS URL: {url!r}")

        attempt = 0
        while True:
            attempt += 1
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req) as resp:  # nosec B310 - scheme checked above
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                # Retry on rate-limit / transient server errors.
                if exc.code in (429, 500, 502, 503, 504) and attempt <= self.max_retries:
                    retry_after = exc.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else min(2 ** attempt, 60)
                    time.sleep(wait)
                    continue
                raise ZenodoError(exc.code, method, url, detail) from None
            except urllib.error.URLError as exc:
                if attempt <= self.max_retries:
                    time.sleep(min(2 ** attempt, 60))
                    continue
                raise ZenodoError(0, method, url, str(exc.reason)) from None

    # -- workflow steps ----------------------------------------------------
    def create_draft(self) -> dict:
        """Create an empty draft; Zenodo pre-reserves a DOI for it."""
        return self._request("POST", f"{self.base}/api/deposit/depositions", json_body={})

    def upload_file(self, bucket_url: str, filename: str, content: bytes) -> dict:
        """Upload raw bytes to the deposition bucket (recommended files API)."""
        return self._request("PUT", f"{bucket_url}/{filename}", data=content)

    def set_metadata(self, dep_id: int, metadata: dict) -> dict:
        url = f"{self.base}/api/deposit/depositions/{dep_id}"
        return self._request("PUT", url, json_body={"metadata": metadata})

    def publish(self, dep_id: int) -> dict:
        url = f"{self.base}/api/deposit/depositions/{dep_id}/actions/publish"
        return self._request("POST", url)

    def get(self, dep_id: int) -> dict:
        return self._request("GET", f"{self.base}/api/deposit/depositions/{dep_id}")


def reserved_doi_of(draft: dict) -> str | None:
    return draft.get("metadata", {}).get("prereserve_doi", {}).get("doi")
