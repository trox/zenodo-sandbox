"""Embed a reserved DOI into a PDF before upload.

Two layers, both applied:

1. Document metadata: writes the DOI into the PDF Info dictionary (a ``/doi``
   key plus the standard ``/Subject``) so it travels with the file and is
   machine-readable.
2. Optional visible stamp: a configurable text overlay (see ``StampSpec``).
   Requires reportlab; if it's not installed the function still succeeds with
   metadata-only embedding.

Originals are never modified — always writes to a new destination path.

Requires: pypdf  (pip install pypdf).  Optional: reportlab (for the stamp).
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

# Track TTFs already registered with reportlab so a batch doesn't re-register
# the same file hundreds of times.
_REGISTERED: "dict[str, str]" = {}

# Where footer_doi_stamp looks for a Calibri (or metric-compatible Carlito) TTF,
# in order. Calibri is proprietary — keep it local, never commit it.
_FONT_SEARCH = [
    os.environ.get("ZENODO_CALIBRI_TTF", ""),
    "fonts/Calibri.ttf",
    "fonts/calibri.ttf",
    "fonts/Carlito-Regular.ttf",
    "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",  # LibreOffice's Calibri clone
]


def find_calibri(explicit: "str | None" = None) -> "str | None":
    """Return a path to a Calibri/Carlito TTF, or None. Checks, in order:
    the explicit arg, $ZENODO_CALIBRI_TTF, ./fonts/, then the system Carlito."""
    for cand in [explicit, *_FONT_SEARCH]:
        if cand and os.path.isfile(cand):
            return cand
    return None


def _register(ttf_path: str, name: str = "Calibri") -> str:
    """Register `ttf_path` with reportlab under `name` (idempotent); return the name."""
    if _REGISTERED.get(name) == ttf_path:
        return name
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont(name, ttf_path))
    _REGISTERED[name] = ttf_path
    return name

# --- Stamp geometry --------------------------------------------------------
# PDF coordinate space: origin bottom-left, Y up, units = points (1/72 inch).
# drawString() places the text BASELINE; glyphs rise `ascent` above it and drop
# `descent` (negative) below. All anchoring is arithmetic on width + asc/desc.

_H = {"left", "center", "right"}
_V = {"top", "middle", "bottom"}


@dataclass
class StampSpec:
    """Fully specifies a text stamp. All lengths in PDF points (72 = 1 inch)."""
    text: str
    anchor: str = "bottom-left"   # "<v>-<h>", v in top/middle/bottom, h in left/center/right
    margin_x: float = 36.0        # distance from the anchored horizontal edge
    margin_y: float = 24.0        # distance from the anchored vertical edge
    font: str = "Helvetica"       # any built-in base-14 font, or a registered TTF name
    size: float = 8.0
    color: tuple = (0.0, 0.0, 0.0)   # RGB, each 0..1
    opacity: float = 1.0             # 0..1 fill alpha (needs a modern PDF viewer)
    rotation: float = 0.0            # degrees CCW, about the anchor point
    box: bool = False                # draw a filled rectangle behind the text
    box_color: tuple = (1.0, 1.0, 1.0)
    box_opacity: float = 1.0
    box_padding: float = 3.0
    pages: str = "first"             # "first" | "last" | "all" | comma list e.g. "1,3,5" (1-based)


def default_doi_stamp(doi: str, **overrides) -> StampSpec:
    """The project default: 'DOI: <doi>   https://doi.org/<doi>', bottom-left."""
    spec = StampSpec(text=f"DOI: {doi}   https://doi.org/{doi}")
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec


def footer_doi_stamp(doi: str, *, calibri_ttf: "str | None" = None, **overrides) -> StampSpec:
    """Preset reverse-engineered from the Gonzalez et al. example PDF.

    Measured spec (first-page footer, A4 595.28 x 841.89 pt):
      text     "DOI: <doi>"          (no URL)
      font     Calibri Regular, 11 pt, black (0,0,0)
      anchor   bottom-left
      baseline x = 71.05, y = 49.16 pt  (visual bottom y0 = 46.19)
      margins  left = 71.05 pt (~2.5 cm), bottom-of-text = 46.19 pt (~1.63 cm)

    Calibri is not a base-14 font. Provide a Calibri.ttf (or the
    metric-compatible Carlito-Regular.ttf) to match glyph widths exactly, via
    the ``calibri_ttf`` arg, ``$ZENODO_CALIBRI_TTF``, or ./fonts/. If none is
    found it falls back to Helvetica — position is identical, the text is ~10%
    wider.
    """
    ttf = find_calibri(calibri_ttf)
    font = _register(ttf, "Calibri") if ttf else "Helvetica"
    spec = StampSpec(
        text=f"DOI: {doi}",
        anchor="bottom-left",
        margin_x=71.05,
        margin_y=46.19,   # 'bottom' anchor pins the text's visual bottom here
        font=font,
        size=11.0,
        color=(0.0, 0.0, 0.0),
        pages="first",
    )
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec


# --- Public API ------------------------------------------------------------
def embed_doi(src_path: str, dst_path: str, doi: str, *,
              stamp: bool = False, stamp_spec: "StampSpec | None" = None) -> None:
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
    if doi not in str(existing_subject):
        meta["/Subject"] = (f"{existing_subject}  " if existing_subject else "") + f"DOI: {doi}"
    writer.add_metadata(meta)

    # 2. Optional visible stamp.
    if stamp or stamp_spec is not None:
        spec = stamp_spec or default_doi_stamp(doi)
        _apply_stamp(writer, spec)

    with open(dst_path, "wb") as fh:
        writer.write(fh)


# --- Rendering -------------------------------------------------------------
def _resolve_pages(spec_pages: str, n: int) -> "list[int]":
    s = spec_pages.strip().lower()
    if s == "first":
        return [0]
    if s == "last":
        return [n - 1]
    if s == "all":
        return list(range(n))
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok:
            i = int(tok) - 1  # 1-based -> 0-based
            if 0 <= i < n:
                out.append(i)
    return out


def _anchor_baseline(anchor: str, W: float, H: float, tw: float,
                     asc: float, desc: float, spec: StampSpec) -> "tuple[float, float]":
    """Return the (x, y) BASELINE for the text in the page coordinate system."""
    try:
        v, h = anchor.split("-", 1)
    except ValueError:
        v, h = "bottom", "left"
    if h not in _H or v not in _V:
        v, h = "bottom", "left"

    if h == "left":
        x = spec.margin_x
    elif h == "right":
        x = W - spec.margin_x - tw
    else:  # center
        x = (W - tw) / 2.0

    if v == "bottom":
        y = spec.margin_y - desc            # desc<0 => visual bottom sits margin_y above edge
    elif v == "top":
        y = H - spec.margin_y - asc
    else:  # middle
        y = (H - asc - desc) / 2.0
    return x, y


def _apply_stamp(writer, spec: StampSpec) -> None:
    """Composite `spec` onto the selected pages. No-op if reportlab is absent."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
    except ImportError:
        return  # keep metadata-only embedding
    from pypdf import PdfReader

    pages = _resolve_pages(spec.pages, len(writer.pages))
    asc_desc = pdfmetrics.getAscentDescent(spec.font, spec.size)  # (ascent, descent<0)
    asc, desc = float(asc_desc[0]), float(asc_desc[1])
    tw = pdfmetrics.stringWidth(spec.text, spec.font, spec.size)

    for idx in pages:
        page = writer.pages[idx]
        # Use the CROPBOX (the visible area) for extents and offset; fall back to mediabox.
        box = page.cropbox if page.cropbox is not None else page.mediabox
        x0, y0 = float(box.left), float(box.bottom)
        W, H = float(box.width), float(box.height)

        buf = io.BytesIO()
        # Overlay canvas spans the full mediabox so merge_page aligns 1:1.
        mb = page.mediabox
        c = canvas.Canvas(buf, pagesize=(float(mb.width), float(mb.height)))

        bx, by = _anchor_baseline(spec.anchor, W, H, tw, asc, desc, spec)
        # Shift into mediabox space by the cropbox origin.
        bx += x0
        by += y0

        c.saveState()
        c.translate(bx, by)
        if spec.rotation:
            c.rotate(spec.rotation)
        if spec.box:
            p = spec.box_padding
            c.setFillColorRGB(*spec.box_color)
            if spec.box_opacity < 1.0:
                c.setFillAlpha(spec.box_opacity)
            c.rect(-p, desc - p, tw + 2 * p, (asc - desc) + 2 * p, stroke=0, fill=1)
        c.setFillColorRGB(*spec.color)
        if spec.opacity < 1.0:
            c.setFillAlpha(spec.opacity)
        c.setFont(spec.font, spec.size)
        c.drawString(0, 0, spec.text)  # baseline at the translated origin
        c.restoreState()
        c.save()
        buf.seek(0)

        overlay = PdfReader(buf).pages[0]
        # NOTE: if the page carries /Rotate (90/180/270) the stamp rotates with
        # the page. For those, add spec.rotation to counter it, or normalize the
        # page with writer.pages[idx].transfer_rotation_to_content() first.
        page.merge_page(overlay)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Embed a DOI into a PDF (metadata + optional stamp).")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("doi")
    ap.add_argument("--stamp", action="store_true", help="Draw the default DOI stamp (needs reportlab).")
    ap.add_argument("--anchor", default="bottom-left")
    ap.add_argument("--size", type=float, default=8.0)
    ap.add_argument("--pages", default="first", help="first | last | all | '1,3,5'")
    ap.add_argument("--box", action="store_true", help="White box behind the text.")
    ap.add_argument("--rotation", type=float, default=0.0)
    a = ap.parse_args()

    spec = None
    if a.stamp or a.box or a.anchor != "bottom-left" or a.pages != "first" \
            or a.size != 8.0 or a.rotation:
        spec = default_doi_stamp(a.doi, anchor=a.anchor, size=a.size, pages=a.pages,
                                 box=a.box, rotation=a.rotation)
    embed_doi(a.src, a.dst, a.doi, stamp=a.stamp, stamp_spec=spec)
    print(f"Embedded {a.doi} -> {a.dst}")
