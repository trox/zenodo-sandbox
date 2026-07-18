# Runbook — from a clean Mac (Apple Silicon) to published DOIs

End-to-end steps to run the batch DOI workflow on an M-series Mac: set up, trial
on the Zenodo sandbox, debug, then execute on production. Read the top of
`README.md` first for what each script does.

> **The one rule that prevents the worst mistake:** the DOI you embed into a PDF
> must come from the **same environment you will publish in**. Sandbox reserves
> `10.5072/zenodo.NNN`; production reserves `10.5281/zenodo.NNN`. A PDF embedded
> during the sandbox trial has the *wrong* DOI for production. **Re-run the batch
> against production to produce the real files** — never publish sandbox-embedded
> PDFs. Use a separate manifest and out-dir per environment.

---

## 1. Set up the environment

```bash
git clone <repo-url> && cd zenodo-sandbox
git checkout claude/zenodo-api-doi-reserve-tskytu

python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt          # pypdf, reportlab (+ pdfminer.six)
```

All dependencies are pure-Python or ship arm64 wheels — nothing compiles, no
Homebrew needed. Python 3.11+ recommended (`python3 --version`).

### Font (for an exact stamp)

If you have Microsoft Office, Calibri is usually at
`~/Library/Fonts/Calibri.ttf` or `/Library/Fonts/Microsoft/Calibri.ttf`.

```bash
cp "/Library/Fonts/Microsoft/Calibri.ttf" fonts/Calibri.ttf   # adjust path
```

No Calibri? Use OFL Carlito (`fonts/Carlito-Regular.ttf`) — the batch finds it
automatically. `fonts/*.ttf` is git-ignored, so the font stays local.

### Tokens

Create **two separate** personal access tokens (separate accounts/sites):

| Environment | Where | Scopes |
|---|---|---|
| Sandbox | https://sandbox.zenodo.org/account/settings/applications/tokens/new/ | `deposit:write`, `deposit:actions` |
| Production | https://zenodo.org/account/settings/applications/tokens/new/ | `deposit:write`, `deposit:actions` |

Keep them out of the shell history / repo:

```bash
echo 'ZENODO_TOKEN=paste-token-here' > .env      # .env is git-ignored
set -a; source .env; set +a                       # load into the shell
```

---

## 2. Prepare inputs

```
pdfs/                 your PDFs, unique filenames
files.csv            one row per PDF (see README schema)
authors.csv          long-format authors, joined on `filename`
```

The batch validates up front that every PDF has exactly one `files.csv` row and
vice versa, and fails loudly on any mismatch — fix those before proceeding.

---

## 3. Trial on the sandbox

Use the **sandbox** token and a small subset first.

```bash
set -a; source .env; set +a                        # sandbox token loaded

python batch_reserve.py --sandbox --stamp --limit 2 \
    --files files.csv --authors authors.csv \
    --pdf-dir ./pdfs --out-dir ./out_sandbox \
    --manifest manifest.sandbox.csv
```

Startup prints the target (`SANDBOX`) and the resolved stamp font — confirm it
says `Calibri <- fonts/Calibri.ttf` and not the Helvetica fallback.

Then verify, in order:

1. **Embedded PDFs** in `./out_sandbox/` — open one: is the DOI in the footer at
   the right spot? Is it in the metadata? (`python -c "from pypdf import
   PdfReader; print(PdfReader('out_sandbox/<f>.pdf').metadata)"`)
2. **Manifest** `manifest.sandbox.csv` — every row `draft_ready`, `error` empty,
   a `reserved_doi` (should start `10.5072/`), a `record_url`.
3. **Drafts on the web** — open each `record_url`: title, authors/affiliations,
   keywords, license, file all correct?
4. **Publish trial** (sandbox is disposable):
   ```bash
   python publish_from_manifest.py --sandbox --manifest manifest.sandbox.csv --list
   python publish_from_manifest.py --sandbox --manifest manifest.sandbox.csv --only <f>.pdf --yes
   ```
   Confirm status flips to `published`. (Sandbox DOIs are test registrations and
   do not resolve at doi.org — that's expected.)

Iterate on `files.csv`/`authors.csv`/the stamp until a couple of records are
perfect, then run the full set on sandbox (drop `--limit`). Delete junk sandbox
drafts from the web UI when done.

---

## 4. Points of attention for debugging

- **`403 Forbidden`** → token scope. `deposit:write` for the batch; publishing
  additionally needs `deposit:actions`. Regenerate the token with both.
- **`401`** → wrong/expired token, or sandbox token used against production (or
  vice versa). They are not interchangeable.
- **`400` on metadata** → usually an invalid `license` id (must be a Zenodo id,
  e.g. `cc-by-4.0`), a missing required field (title/description/creators), or an
  `upload_type` needing a sub-type (`publication` → `publication_type`,
  `image` → `image_type`). The error body names the field.
- **`429`** → rate limit; the client already backs off and retries. For hundreds
  of files just let it run; don't parallelize.
- **Helvetica instead of Calibri** → the startup line said fallback. Put the TTF
  in `fonts/` or pass `--font-file`.
- **Stamp looks rotated/misplaced** → that PDF has a `/Rotate` flag (scanned or
  landscape page). See the `/Rotate` caveat in `README.md`.
- **CSV encoding / accents wrong** → export the CSVs as UTF-8 (the reader accepts
  a BOM). Author `name` must be `Family, Given`.
- **Re-running seems to skip files** → by design. The manifest resumes each file
  from its last status. To start clean, use a fresh `--manifest` and `--out-dir`.
- **Interrupted run** → safe to re-run the same command; it continues where it
  stopped and never mints duplicate DOIs.

---

## 5. Route to production

Only after the sandbox full run is clean.

```bash
# swap in the PRODUCTION token
echo 'ZENODO_TOKEN=paste-PROD-token' > .env
set -a; source .env; set +a

# fresh manifest + out-dir so real DOIs get embedded into fresh PDFs
python batch_reserve.py --stamp \
    --files files.csv --authors authors.csv \
    --pdf-dir ./pdfs --out-dir ./out_prod \
    --manifest manifest.prod.csv
```

Startup must say `PRODUCTION`. This reserves **real** `10.5281/zenodo.NNN` DOIs,
embeds each into a fresh PDF in `./out_prod/`, uploads, sets metadata, and stops
at draft. **Nothing is public yet.**

Review, then publish deliberately:

```bash
python publish_from_manifest.py --manifest manifest.prod.csv --list          # dry run
python publish_from_manifest.py --manifest manifest.prod.csv --only <f>.pdf --yes   # one first
#   → open its record, confirm https://doi.org/10.5281/zenodo.NNN resolves
python publish_from_manifest.py --manifest manifest.prod.csv --yes           # the rest
```

Publishing is **permanent**: the DOI is registered with DataCite and the files
are frozen (further changes require a new *version*).

### After

- Keep `manifest.prod.csv` — it is your filename → DOI → record map of record.
- Optionally add the records to a Zenodo community from each record page.
- Abandoned drafts (never published) can be deleted from the web UI at no cost.
