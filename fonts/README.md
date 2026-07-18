# Fonts

Drop **`Calibri.ttf`** here to reproduce the example footer's glyphs exactly.

`footer_doi_stamp()` looks for a font in this order:
1. an explicit `calibri_ttf=` argument (or `--font-file` on the CLI)
2. the `$ZENODO_CALIBRI_TTF` environment variable
3. `fonts/Calibri.ttf`, `fonts/calibri.ttf`, `fonts/Carlito-Regular.ttf`
4. the system Carlito (`/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf`)

If none is found it falls back to Helvetica: identical position, ~10% wider text.

## Licensing — do not commit Calibri

Calibri is a proprietary Microsoft font; `*.ttf` here is git-ignored on purpose.
Keep your licensed copy local. For a redistributable, metrically-compatible
substitute use **Carlito** (`Carlito-Regular.ttf`, ships with LibreOffice, SIL
Open Font License) — rename it to `Calibri.ttf` or point `--font-file` at it.
