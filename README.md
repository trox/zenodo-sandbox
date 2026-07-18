# zenodo-sandbox

Reserving a DOI via the [Zenodo API](https://zenodo.org/api).

## The point of confusion

The API **can** reserve a DOI for you — you do **not** have to provide one.
The `doi` field in deposition metadata is for the *opposite* case: registering a
DOI that a publisher already assigned. Two different fields:

| Field | Who fills it | Meaning |
|-------|--------------|---------|
| `doi` | You | An **existing external** DOI. Leave empty and Zenodo mints one. |
| `prereserve_doi` | Zenodo | A **Zenodo-minted** DOI, auto-generated and read-only. |

## How to reserve

Create an **empty draft deposition** — Zenodo automatically pre-reserves a DOI
and returns it in the response:

```bash
curl -X POST "https://zenodo.org/api/deposit/depositions" \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response (trimmed):

```json
{
  "id": 1234567,
  "metadata": {
    "prereserve_doi": { "doi": "10.5281/zenodo.1234567", "recid": 1234567 }
  }
}
```

`metadata.prereserve_doi.doi` is your reserved DOI (pattern
`10.5281/zenodo.<recid>`).

Notes:

- The DOI is **not registered with DataCite until you publish**, so it will not
  resolve before then — but it is reserved and safe to embed in your files.
- Do **not** copy it into the `doi` field yourself; that field is only for
  external DOIs, and setting it tells Zenodo *not* to mint one.
- For a new version of an existing record, Zenodo pre-reserves a fresh DOI as
  soon as you create the new-version draft.

## Script

```bash
export ZENODO_TOKEN=...            # token with the 'deposit:write' scope
python reserve_doi.py              # production zenodo.org
python reserve_doi.py --sandbox    # sandbox.zenodo.org (recommended for testing)
```

Tokens: <https://zenodo.org/account/settings/applications/tokens/new/>
(sandbox: <https://sandbox.zenodo.org/account/settings/applications/tokens/new/>).

## Full flow: reserve -> upload -> metadata -> publish

The complete lifecycle over the Deposit API is four calls. `upload_and_publish.py`
runs all of them.

```bash
export ZENODO_TOKEN=...   # needs BOTH 'deposit:write' and 'deposit:actions' scopes

# Leaves an unpublished draft you can review in the web UI:
python upload_and_publish.py ./data.csv --sandbox \
  --title "My dataset" --creator "Doe, Jane" --affiliation "Rotterdam UAS" \
  --description "Example upload." --upload-type dataset

# Same, but actually publishes (PERMANENT — registers the DOI, freezes files):
python upload_and_publish.py ./data.csv --sandbox --publish
```

### 1. Create the draft (DOI reserved automatically)

```bash
curl -X POST "https://zenodo.org/api/deposit/depositions" \
  -H "Authorization: Bearer $ZENODO_TOKEN" -H "Content-Type: application/json" -d '{}'
```

Keep two things from the response: `id` and `links.bucket` (the upload URL).

### 2. Upload the file (bucket API — recommended, handles large files)

`PUT` the raw file bytes to `{bucket_url}/{filename}`:

```bash
curl -X PUT "$BUCKET_URL/data.csv" \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  --upload-file ./data.csv
```

(The older `POST /api/deposit/depositions/{id}/files` multipart form still works
but is deprecated.)

### 3. Set the minimum required metadata

To be publishable you need at least `title`, `upload_type`, `description`, and
`creators`:

```bash
curl -X PUT "https://zenodo.org/api/deposit/depositions/$ID" \
  -H "Authorization: Bearer $ZENODO_TOKEN" -H "Content-Type: application/json" \
  -d '{
        "metadata": {
          "title": "My dataset",
          "upload_type": "dataset",
          "description": "Example upload.",
          "creators": [{"name": "Doe, Jane", "affiliation": "Rotterdam UAS"}]
        }
      }'
```

Some `upload_type`s need an extra field: `publication` requires
`publication_type`, `image` requires `image_type`.

### 4. Publish (permanent)

```bash
curl -X POST "https://zenodo.org/api/deposit/depositions/$ID/actions/publish" \
  -H "Authorization: Bearer $ZENODO_TOKEN"
```

Publishing **registers the reserved DOI with DataCite and freezes the files** —
after this you can only create a new *version*, not edit the files. Always dry-run
on `sandbox.zenodo.org` first. The `actions/publish` call requires the
`deposit:actions` token scope.

## Batch workflow: many PDFs, DOI embedded before publish

Scenario: a folder of PDFs (unique filenames), extensive metadata in CSV
(multiple authors), each PDF needs its own DOI **embedded into the PDF before
upload**, and publishing stays a manual final check.

Because a DOI belongs to a record, **one PDF = one record = one DOI**. The DOI
must exist before the file is finalized, which is exactly what reserving solves:

```
reserve DOI  ->  embed into the PDF  ->  upload  ->  set metadata  ->  STOP (draft)
                                                                        |
                                                       manual review + publish
```

### Files

| Script | Role |
|--------|------|
| `zenodo_api.py` | Small Deposit API client (ret/backoff on 429/5xx). |
| `embed_doi.py` | Writes the DOI into a PDF: `/doi` + `/Subject` metadata, and an optional visible stamp on page 1 (`--stamp`, needs reportlab). |
| `batch_reserve.py` | Driver: reserve → embed → upload → describe, per file, resumable via `manifest.csv`. **Never publishes.** |
| `publish_from_manifest.py` | Separate, gated final step: publishes `draft_ready` rows. |

### Two-table CSV (handles multiple authors)

`files.csv` — one row per PDF, keyed by `filename`:

```
filename,title,description,upload_type,keywords,license,version,publication_date
paper1.pdf,"Effects of X on Y","A study.",publication,"biology;experiment",cc-by-4.0,1.0,2026-07-18
```

`authors.csv` — long format, one row per (file, author), joined on `filename`,
ordered by `order`:

```
filename,order,name,affiliation,orcid
paper1.pdf,1,"Doe, Jane","Rotterdam UAS",0000-0001-2345-6789
paper1.pdf,2,"Smith, John","MIT",
```

`name` must be **"Family, Given"**; empty `affiliation`/`orcid` cells are
omitted (not sent as `""`). `keywords` is `;`-separated. Non-author contributors
(editors, supervisors) belong in a `contributors` list instead — add a column
and extend `build_metadata` if you need them.

### Run it

```bash
pip install -r requirements.txt          # pypdf (+ reportlab for --stamp)
export ZENODO_TOKEN=...                   # scope 'deposit:write'

python batch_reserve.py --sandbox \
  --files files.csv --authors authors.csv \
  --pdf-dir ./pdfs --out-dir ./pdfs_with_doi --stamp
```

This validates that every PDF has exactly one metadata row (and vice versa),
then for each file: reserves a DOI, writes a DOI-embedded copy into
`./pdfs_with_doi/`, uploads it, sets metadata, and records progress in
`manifest.csv`. **Originals are never modified.** Re-running resumes each file
from its last recorded status, so an interrupted or partially-failed run is safe
to repeat — it will not mint duplicate DOIs.

`manifest.csv` is your control sheet:

```
filename,status,deposition_id,reserved_doi,bucket_url,record_url,error
```

Statuses advance `reserved → embedded → uploaded → described → draft_ready`.

### The DOI stamp

The visible stamp is configurable via `StampSpec` in `embed_doi.py`. Coordinate
model: PDF points (72 = 1 inch), origin bottom-left, Y up; `drawString` sets the
text **baseline**, so anchoring is arithmetic on `stringWidth` + font
ascent/descent (`pdfmetrics.getAscentDescent`). Extents come from the page
**cropbox** (visible area), and the overlay is rendered with reportlab and
composited via `pypdf.merge_page`.

Default: `DOI: <doi>   https://doi.org/<doi>`, Helvetica 8 pt, black, bottom-left
at 36 pt / 24 pt margins, first page only.

```python
from embed_doi import embed_doi, default_doi_stamp

spec = default_doi_stamp(
    "10.5281/zenodo.123",
    anchor="bottom-right",   # {top,middle,bottom}-{left,center,right}
    size=9, box=True, box_color=(1, 1, 1), box_opacity=0.7,
    pages="all",             # first | last | all | "1,3,5"
)
embed_doi("in.pdf", "out.pdf", "10.5281/zenodo.123", stamp_spec=spec)
```

`StampSpec` fields: `text, anchor, margin_x, margin_y, font, size, color,
opacity, rotation, box, box_color, box_opacity, box_padding, pages`. CLI:

```bash
python embed_doi.py in.pdf out.pdf 10.5281/zenodo.123 \
    --anchor top-right --size 9 --box --pages all
```

Caveat: on pages that carry a `/Rotate` flag (90/180/270) the stamp rotates with
the page — counter it with `rotation=`, or normalize first via
`page.transfer_rotation_to_content()`.

#### Spec measured from the Gonzalez et al. example

Reverse-engineered with `pdfminer.six` from the real footer (`footer_doi_stamp()`):

| Property | Measured value |
|---|---|
| Text | `DOI: 10.5281/zenodo.13221337` (no URL) |
| Font | **Calibri Regular** (subset `AAAAAC+Calibri`), not bold/italic |
| Size | 11 pt (effective 11.04) |
| Color | Black `(0, 0, 0)` |
| Page | A4, 595.28 × 841.89 pt; first page only |
| Anchor | Bottom-left |
| Baseline | x = 71.05, y = 49.16 pt |
| Text bbox | x0=71.05, y0=46.19, x1=212.43, y1=57.23 (w=141.38, h=11.04) |
| Left margin | 71.05 pt (≈ 2.5 cm) |
| Bottom (visual) | 46.19 pt (≈ 1.63 cm) from the page edge |

```python
from embed_doi import embed_doi, footer_doi_stamp
# Exact position + size + colour; Helvetica substitute (~10% wider text):
embed_doi("in.pdf", "out.pdf", doi, stamp_spec=footer_doi_stamp(doi))
# Pixel-exact glyphs — supply Calibri (or metric-compatible Carlito-Regular.ttf):
embed_doi("in.pdf", "out.pdf", doi,
          stamp_spec=footer_doi_stamp(doi, calibri_ttf="/path/to/Carlito-Regular.ttf"))
```

Verified: `footer_doi_stamp` reproduces the left edge and baseline to **0.00 pt**
and the cap height to 0.04 pt. Calibri is not a base-14 font, so without a
Calibri/Carlito TTF the glyph *widths* differ (~15 pt longer) — position is
unaffected.

**Supplying Calibri.** `footer_doi_stamp` finds the font in this order: the
`calibri_ttf=` arg (`--font-file`), `$ZENODO_CALIBRI_TTF`, `fonts/Calibri.ttf`,
then the system Carlito. Drop your licensed `Calibri.ttf` into `fonts/` — it is
git-ignored (Calibri is proprietary; see `fonts/README.md`). Carlito is a free,
metric-compatible drop-in.

In the batch, `--stamp` defaults to this footer style:

```bash
# with fonts/Calibri.ttf present, glyphs match the example exactly:
python batch_reserve.py --sandbox --stamp \
    --files files.csv --authors authors.csv --pdf-dir ./pdfs --out-dir ./pdfs_with_doi
# or point at the font explicitly:
python batch_reserve.py --sandbox --stamp --font-file /path/to/Calibri.ttf ...
# switch to the URL-style stamp instead:
python batch_reserve.py --sandbox --stamp --stamp-style default ...
```

### Manual publish (final check)

Review each draft via its `record_url`, then publish — one, or all:

```bash
export ZENODO_TOKEN=...   # scopes 'deposit:write' AND 'deposit:actions'
python publish_from_manifest.py --sandbox --list            # dry run
python publish_from_manifest.py --sandbox --only paper1.pdf --yes
python publish_from_manifest.py --sandbox --yes             # all draft_ready
```

Publishing is permanent (DOI registered, files frozen). Rehearse the whole
thing on `sandbox.zenodo.org` first — the reserved DOI you embedded is the exact
DOI that gets registered.

## Newer InvenioRDM PIDs endpoint

Zenodo now runs on InvenioRDM. The legacy Deposit API above still works and is
the simplest route. The InvenioRDM-native equivalent is to create a draft and
then explicitly reserve the DOI:

```bash
# 1. create a draft record  -> returns {"id": "<recid>", ...}
curl -X POST "https://zenodo.org/api/records" \
  -H "Authorization: Bearer $ZENODO_TOKEN" -H "Content-Type: application/json" -d '{...}'

# 2. reserve the DOI for that draft
curl -X POST "https://zenodo.org/api/records/<recid>/draft/pids/doi" \
  -H "Authorization: Bearer $ZENODO_TOKEN"
```
