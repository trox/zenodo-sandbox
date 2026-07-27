# Provenance & authorship

This document records, honestly, how this repository was produced. It exists so
that (a) the copyright/licensing status is unambiguous and (b) anyone assessing
the project — including under Codeberg's Terms of Use § 2 (1) — can see exactly
what was human-directed and what was machine-generated. Nothing here is intended
to overstate human authorship of the code.

## How the work was divided

**Human — P. Troxler (Rotterdam University of Applied Sciences)**
- Originated the problem and the goal.
- Supplied the domain requirements and constraints that shaped the design:
  reserve a DOI *before* the file is finalized; one DOI per file; embed the DOI
  into each PDF footer prior to upload; keep publishing a deliberate, manual
  step; operate as a batch over a folder of PDFs; carry extensive per-file
  metadata (including multiple authors) from CSV.
- Made the key design decisions: the two-table CSV schema, PDF as the target
  file type, the specific footer-stamp style (from a supplied real example
  document), and the choice of hosting/target platforms.
- Reviewed, tested, corrected, and accepted each step; holds final authority and
  maintains the project.

**Machine — Claude (Anthropic)**
- Generated the design proposals and effectively all of the source code and
  prose documentation.
- Proposed the concrete architecture (manifest-based resumable pipeline, the
  `StampSpec` model, the retrying Deposit-API client) as options for the human
  to choose among and direct.
- Measured the example PDF's footer geometry and produced the matching preset.
- Ran the static analysis and dependency checks recorded in `REVIEW.md`.
- Operated throughout under the human's direction and review.

## Method

Development was interactive and iterative, with a human in the loop at every
step: the human set goals and constraints, the model proposed and implemented,
and the human reviewed and steered before anything was kept. No code was
committed without human review.

## Honest note on "how much is AI-written"

By raw line count, the code in this repository is predominantly AI-generated.
The requirements, the design decisions, the review, and the responsibility for
the result are human. We state this plainly rather than obscure it; the CC0
dedication in `LICENSE` is intended to remove any resulting copyright ambiguity,
and `REVIEW.md` documents the safeguards against harmful code.
