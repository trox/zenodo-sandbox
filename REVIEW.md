# Security & harmful-code review

Purpose: document a repeatable protocol and its results, establishing that this
repository contains no harmful code — the safeguard Codeberg's Terms of Use
§ 2 (1) 5 asks for. This is deliberately tool-based and human-signed, not a
self-assessment by the code's generator.

- **Date:** 2026-07-27
- **Reviewer (sign-off):** _______________________  (maintainer, P. Troxler)
- **Commit reviewed:** _______________________  (fill in the SHA you sign off on)

## 1. § 2 (1) 5 analysis (does it apply?)

§ 2 (1) 5 prohibits (a) "harmful code that can be run accidentally during normal
development workflow" and (b) software written to harm other computers. Assessed
against the actual code:

- **No code executes on clone/checkout/install.** There is no `setup.py`,
  `setup.cfg`, `pyproject` build hook, `conftest.py`, CI workflow, entry point,
  or postinstall step. Every script runs only when the user explicitly invokes
  it. (Verified by inspection — none of those files exist.)
- **No dynamic code execution or shell-out.** No `eval`, `exec`, `compile`,
  `__import__`, `os.system`, `subprocess`, `pickle`, or `marshal` anywhere in
  the codebase. (Verified by `grep`.)
- **Not offensive software.** The tool reserves DOIs and uploads PDFs to Zenodo.
- **Network egress is limited and explicit:** HTTPS only, to `zenodo.org` /
  `sandbox.zenodo.org` (the host the user selects), authenticated with the
  user's own token. `https://doi.org/...` appears only as text embedded into the
  stamped PDF, not as a network call. No telemetry, no callbacks.

Conclusion: the repository **complies with § 2 (1) 5**.

## 2. Tooling

Objective, third-party checks (not the model's opinion):

| Check | Tool | Result |
|-------|------|--------|
| Dependency vulnerabilities | `pip-audit -r requirements.txt` | **No known vulnerabilities.** |
| Static security analysis | `bandit -r . -x ./.venv,./pdfs` | **0 live issues.** |

### bandit note
The only findings were three `B310` flags on `urllib.request.urlopen` — a
generic caution that `urlopen` could open `file://` or custom schemes. Each call
site now validates the URL begins with `https://` before opening, and carries a
`# nosec B310` annotation referencing that guard. After the fix bandit reports
0 issues (3 skipped via documented `nosec`).

## 3. Reproduce this review

```bash
pip install bandit pip-audit
pip-audit -r requirements.txt
bandit -r . -x ./.venv,./pdfs

# confirm the negative findings:
grep -rEn "\b(eval|exec|os\.system|subprocess|pickle|marshal|__import__|compile)\b" --include=*.py .
ls setup.py setup.cfg conftest.py .github 2>/dev/null   # expect: none
```

## 4. Handling secrets

Zenodo API tokens are never stored in the repository: they are read from the
`ZENODO_TOKEN` environment variable, and `.env`, manifests, and input PDFs are
git-ignored. Reviewers should confirm no token has been committed
(`git log -p | grep -i token`).

## 5. Human sign-off

The maintainer confirms they have read the code, run the checks above, and take
responsibility for the result. Signature/date at the top of this file.
