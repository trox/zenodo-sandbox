"""Embed a reserved DOI into a PDF before upload.

Two layers, both applied:

1. Document metadata: writes the DOI into the PDF Info dictionary (a ``/doi``
   key plus the standard ``/Subject``) so it travels with the file and is
   machine-readable.
2. Optional visible stamp: prints "DOI: 10.5281/zenodo.NNNN  https://doi.org/..."
   at the bottom of the first page. Requires reportlab; if it's not installed
   the function still succeeds with metadata-only embedding.

Originals are never modified — always writes to a new destination path.

Requires: pypdf  (pip install pypdf).  Optional: reportlab (for --stamp).
"""
from __future__ import annotations

import io


def embed_doi(src_path: str, dst_path: str, doi: str, *, stamp: bool = False) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(src_path)
    writer = PdfWriter()
    writer.append(reader)

    # 1. Metadata layer — preserve existing keys, add the DOI.
    meta = {}
    if reader.metadata:
        meta.update({k: v for k, v in reader.metadata.items() if v is not None})
    meta["/doi"] = doi
    existing_subject = meta.get("/Subject", "")
    doi_url = f"https://doi.org/{doi}"
    if doi not in str(existing_subject):
        meta["/Subject"] = (f"{existing_subject}  " if existing_subject else "") + f"DOI: {doi}"
    writer.add_metadata(meta)

    # 2. Optional visible stamp on page 1.
    if stamp:
        _stamp_first_page(writer, f"DOI: {doi}   {doi_url}")

    with open(dst_path, "wb") as fh:
        writer.write(fh)


def _stamp_first_page(writer, text: str) -> None:
    """Overlay `text` near the bottom-left of the first page. No-op if reportlab absent."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        # reportlab not installed: silently keep metadata-only embedding.
        return
    from pypdf import PdfReader

    if not writer.pages:
        return
    page = writer.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica", 8)
    c.drawString(36, 24, text)  # 0.5" from the left, 0.33" from the bottom
    c.save()
    buf.seek(0)

    overlay = PdfReader(buf).pages[0]
    page.merge_page(overlay)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Embed a DOI into a PDF.")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("doi")
    ap.add_argument("--stamp", action="store_true", help="Also print the DOI on page 1 (needs reportlab).")
    a = ap.parse_args()
    embed_doi(a.src, a.dst, a.doi, stamp=a.stamp)
    print(f"Embedded {a.doi} -> {a.dst}")
