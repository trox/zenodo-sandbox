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
