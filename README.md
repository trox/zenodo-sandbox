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
