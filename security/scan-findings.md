# Deterministic security scans: findings and triage

| | |
|---|---|
| Date | 2026-10-21 |
| Commit scanned | `c7c9a10` (`main`, after PR #1 merge `987a7fc`) |
| Run by | AI agent (Claude Code), locally on Windows; tools pinned as below |
| Raw outputs | [`security/scans/`](scans/): unmodified tool output |
| Result | **0 vulnerabilities, 0 leaked secrets, 0 code findings.** One coverage gap (Semgrep parse error on a security-relevant file) was closed with a regression test. |

## Summary

| Scanner | Version | Target | Raw output | Findings |
|---|---|---|---|---|
| Semgrep (`--config auto`, 512 rules) | 1.182.0 | 118 tracked files | [`semgrep.json`](scans/semgrep.json) | **0** findings, 4 parse errors (triaged below) |
| pip-audit (OSV/PyPI advisories) | 2.10.1 | 29 runtime packages from `uv.lock` | [`pip-audit.json`](scans/pip-audit.json) | **0** |
| pip-audit, dev group (informational) | 2.10.1 | 15 dev packages from `uv.lock` | [`pip-audit-dev.json`](scans/pip-audit-dev.json) | **0** |
| npm audit `--omit=dev` | npm 11.17.0 | 10 production packages | [`npm-audit.json`](scans/npm-audit.json) | **0** |
| npm audit, all (informational) | npm 11.17.0 | 152 packages incl. dev | [`npm-audit-all.json`](scans/npm-audit-all.json) | **0** |
| gitleaks (`git` mode, `--redact`) | 8.30.1 | full history, all 16 non-merge commits (~847 KB) | [`gitleaks.json`](scans/gitleaks.json) | **0** leaks |

## Commands

Run from the repo root (PowerShell users: run in Git Bash, or translate `$(pwd -W)` to `${PWD}`).

```bash
# Semgrep: same config as CI, JSON output
docker run --rm -v "$(pwd -W):/src" -w /src semgrep/semgrep:1.182.0 \
  semgrep scan --config auto --json --output /src/security/scans/semgrep.json

# pip-audit on the exact locked versions (no resolution: --no-deps --disable-pip)
cd backend
uv export --locked --no-dev    --no-emit-project --format requirements-txt -o req-prod.txt
uv export --locked --only-dev  --no-emit-project --format requirements-txt -o req-dev.txt
uvx --from pip-audit==2.10.1 pip-audit -r req-prod.txt --no-deps --disable-pip --format json -o ../security/scans/pip-audit.json
uvx --from pip-audit==2.10.1 pip-audit -r req-dev.txt  --no-deps --disable-pip --format json -o ../security/scans/pip-audit-dev.json
cd ..

# npm audit: production dependencies (what ships in the bundle), then everything
cd frontend
npm audit --omit=dev --json > ../security/scans/npm-audit.json
npm audit --json            > ../security/scans/npm-audit-all.json
cd ..

# gitleaks over the whole git history; --redact so a match never lands in the report
docker run --rm -v "$(pwd -W):/repo" -w /repo zricethezav/gitleaks:v8.30.1 \
  git /repo --redact --report-format json --report-path /repo/security/scans/gitleaks.json
```

## Triage

Each scanner's findings and gaps, with a status: fixed / false positive / accepted risk.

### S1 — Semgrep cannot parse `backend/app/services/tracking_codes.py`: **fixed (coverage gap closed)**

- **Output:** `semgrep.json` → `errors[]`: `Syntax error at line backend/app/services/tracking_codes.py:43: [ was unexpected`.
- **Cause:** line 43 uses Python 3.12 generic function syntax (PEP 695), `def create_with_unique_code[T](...)`, which Semgrep 1.182.0's Python parser does not support. The **whole file** is skipped, in CI too.
- **Why it matters:** this module generates tracking codes, the only secret protecting `/api/public/track/{code}`. A rule like `python.lang.security.insecure-random` would not see a regression from `secrets.choice` to `random.choice` here.
- **Manual review:** `generate_tracking_code` defaults to `secrets.choice` (CSPRNG) over a 30-character alphabet, 5 characters long; there is no other randomness in the file. OK.
- **Resolution:** added `tests/unit/test_tracking_codes.py::test_generation_defaults_to_a_cryptographically_secure_choice`, which asserts the default **is** `secrets.choice`, so the regression Semgrep can't see fails the unit tests. The generic syntax was not rewritten to `TypeVar` just to suit the scanner: ruff's pyupgrade rules (`UP`) target Python 3.12 syntax, and suppressing a linter to satisfy a scanner was rejected (AGENTS.md: don't disable linters or scanners).

### S2 — Semgrep partial parse of 3 frontend test files: **accepted (test-only code)**

- **Output:** `PartialParsing` in `frontend/src/components/StatusChangeControl.test.tsx:11`, `frontend/src/pages/SignInPage.test.tsx:11` and `frontend/src/pages/TrackPage.test.tsx:11`.
- **Cause:** `importOriginal<typeof import('../api/client')>()`, a TypeScript generic with an `import()` type, inside `vi.mock` factories.
- **Reason for accepting:** only that expression is skipped (partial parse); the rest of each file is scanned. These are Vitest mocks that never ship in the production bundle, and the code they mock (`src/api/client.ts`) parses fine.

### S3 — pip-audit "hashes" warning: **false positive / informational**

- **Output:** `--no-deps is supported, but users are encouraged to fully hash their pinned dependencies`.
- **Reason:** the requirements come from `uv export --locked`, which pins every package from `uv.lock` (itself hash-locked, installed with `uv sync --locked` in CI and the Dockerfile). `--no-deps --disable-pip` audits exactly those versions without re-resolving.

### S4 — No vulnerable dependencies: **no action**

pip-audit (runtime and dev) and npm audit (production and all) report 0 known vulnerabilities. Dev-only tools (Vitest, oxlint, Vite, pytest, ruff…) don't ship in the image's runtime stage: the Node stage only produces `dist/`, and the Python stage installs `--no-dev`.

### S5 — No secrets in git history: **no action**

gitleaks scanned all 16 non-merge commits; the single merge commit (`987a7fc`) adds no content of its own. `.env` was never committed (`git log --all -- .env backend/.env` is empty), and no `.env`, `.db`, `.pem` or key files are tracked. Fictional values that look like tokens (`fictional-staff-token-for-tests`, `ci-smoke-test-token-fictional-0000`, the `change-me` placeholder) are not flagged. The working-tree `.env` (git-ignored, holds the real local token) was deliberately **not** scanned, so its value never appears in any report.

## Limits of these scans

- **Semgrep `auto`** is a pattern scan, not data-flow analysis across functions. PR #1's F1 (trusting `X-Forwarded-For` via a uvicorn CLI flag in a shell script) was found by manual review, not by Semgrep.
- **pip-audit / npm audit** see only *known, published* advisories for exact versions. They don't cover the base images (`python:3.12-slim`, `node:24-slim`, `postgres:16-alpine`): an image scan (e.g. Trivy) is a possible follow-up.
- **gitleaks** checks git history only, not Render or GitHub settings. Secrets live only in Render environment variables and GitHub Actions secrets, which were never read.
- Only Semgrep runs on every PR (`ci.yml`). pip-audit, npm audit and gitleaks are run manually for this report; adding them to CI is a possible follow-up, not done here.
