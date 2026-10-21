# Deterministic security scans: findings and triage

| | |
|---|---|
| Date | 2026-10-21 |
| Commit scanned | `c7c9a10` (`main`, after PR #1 merge `987a7fc`); Trivy: image built from `35600f8` plus the Dockerfile hardening in this step |
| Run by | AI agent (Claude Code), locally on Windows; tools pinned as below |
| Raw outputs | [`security/scans/`](scans/): unmodified tool output |
| Result | Code and dependencies: **0 vulnerabilities, 0 leaked secrets, 0 code findings**; one Semgrep coverage gap closed with a regression test. Container image (Trivy): **0 CRITICAL, 44 HIGH = 8 distinct Debian CVEs, none with an upstream fix**. Fixed what was fixable (latest base digests, setuid/setgid bits stripped, `no-new-privileges`); the rest accepted with reasons (S6). |

## Summary

| Scanner | Version | Target | Raw output | Findings |
|---|---|---|---|---|
| Semgrep (`--config auto`, 512 rules) | 1.182.0 | 118 tracked files | [`semgrep.json`](scans/semgrep.json) | **0** findings, 4 parse errors (triaged below) |
| pip-audit (OSV/PyPI advisories) | 2.10.1 | 29 runtime packages from `uv.lock` | [`pip-audit.json`](scans/pip-audit.json) | **0** |
| pip-audit, dev group (informational) | 2.10.1 | 15 dev packages from `uv.lock` | [`pip-audit-dev.json`](scans/pip-audit-dev.json) | **0** |
| npm audit `--omit=dev` | npm 11.17.0 | 10 production packages | [`npm-audit.json`](scans/npm-audit.json) | **0** |
| npm audit, all (informational) | npm 11.17.0 | 152 packages incl. dev | [`npm-audit-all.json`](scans/npm-audit-all.json) | **0** |
| gitleaks (`git` mode, `--redact`) | 8.30.1 | full history, all 16 non-merge commits (~847 KB) | [`gitleaks.json`](scans/gitleaks.json) | **0** leaks |
| Trivy image (`--severity HIGH,CRITICAL`) | 0.76.0 | `benchtrack:local` (Debian 13.7 base + `/app/.venv`), final hardened build | [`trivy-image.json`](scans/trivy-image.json), [`trivy-image.txt`](scans/trivy-image.txt); before hardening: [`trivy-image-before-hardening.json`](scans/trivy-image-before-hardening.json) | **0** CRITICAL, **44** HIGH (OS packages, 8 CVEs, all unfixed upstream); Python packages **0** |

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

# Trivy on the locally built image (rebuild with the latest bases first)
docker compose build --pull app
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ \
  aquasec/trivy:0.76.0 image --severity HIGH,CRITICAL --format json --quiet benchtrack:local \
  > security/scans/trivy-image.json
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

### S6 — Trivy: 44 HIGH OS-package findings in the image, no upstream fix: **partly fixed, rest accepted**

**Scope.** `benchtrack:local` built from `main` (`35600f8`) with `docker compose build --pull`: base `python:3.12-slim@sha256:2259debdc6af…` (Debian 13.7, published 2026-10-21) and Node stage `node:24-slim@sha256:91acba91b842…`. Only the runtime stage ships. Trivy DB as of 2026-10-21 06:33 UTC.

**Result.** 0 CRITICAL. 44 HIGH entries are 8 distinct CVEs across Debian base packages. All are `affected` or `fix_deferred` in Debian, with no `FixedVersion`. The Python target (the app's virtualenv) has **0**, consistent with pip-audit.

| CVE | Packages (entries) | Debian status | Needs | Reachable in BenchTrack? |
|---|---|---|---|---|
| CVE-2026-76642 | util-linux family: `mount`, `util-linux`, `login`, `bsdutils`, `libmount1`, `libblkid1`, `libuuid1`, `libsmartcols1`, `liblastlog2-2` (9) | affected, no fix | a privileged `mount` with an external helper | No. The app never runs `mount`. **setuid `mount`/`umount`/`su` bits are now stripped**, the user is uid 10001, and the container has no `CAP_SYS_ADMIN`. |
| CVE-2026-78408 | same 9 | affected, no fix | privileged `nsenter --join-cgroup` | No. `nsenter` is never run, and an unprivileged user cannot enter namespaces. |
| CVE-2026-78409 | same 9 | affected, no fix | privileged mount with `X-mount.subdir` | No (as CVE-2026-76642). |
| CVE-2026-78410 | same 9 | affected, no fix | privileged bind mount with `X-mount.owner/group/mode` | No (as CVE-2026-76642). |
| CVE-2026-54369 | `libacl1` (1) | affected, no fix | a privileged process applying ACLs on attacker-controlled symlinks | No. The app doesn't use ACLs (`setfacl` is not installed), and nothing in the container runs privileged. |
| CVE-2025-69720 | ncurses: `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` (4) | affected, no fix | a program parsing crafted terminfo/terminal data | No. The app has no TTY or terminal UI and doesn't import `curses`. |
| CVE-2026-16742 | systemd: `libsystemd0`, `libudev1` (2) | affected, no fix | `systemd-homed` running | No. There is no systemd or `homectl` in the container, only client libraries. |
| CVE-2026-9538 | `perl-base` (1) | fix_deferred | Perl Archive::Tar extracting a crafted tar | No. Perl is never invoked, and the app does not handle archives. |

**Fixed in this step:**
- **Base images refreshed:** `docker compose build --pull` pulled the latest `python:3.12-slim` and `node:24-slim`. They were already the newest published digests, so the findings did not change. A bump only helps once Debian ships fixes; see re-evaluation below.
- **setuid/setgid binaries removed** (`Dockerfile`, runtime stage): the base shipped 11 (`su`, `mount`, `umount`, `passwd`, `chsh`, `chfn`, `gpasswd`, `newgrp`, `chage`, `expiry`, `unix_chkpwd`). The app needs none, so the build strips the bits and **fails if any remain**. This removes the privilege-escalation path of the four util-linux CVEs: an attacker with code execution as `benchtrack` can no longer run a root-owned setuid `mount` or `su`. Verified: `find / -xdev -perm /6000` → 0 files; the container is healthy, `/api/health` and `/` answer, and seeding works.
- **`no-new-privileges:true`** on the Compose `app` service, so no process can gain privileges even if a setuid file reappeared. Render does not expose this option; the setuid strip covers Render.

Trivy still lists the 44 entries after hardening, because it reports installed package versions, not exploitability: [`trivy-image-before-hardening.json`](scans/trivy-image-before-hardening.json) vs [`trivy-image.json`](scans/trivy-image.json).

**Accepted, with reasons:**
- No fixed package exists for any of the 8 CVEs (Debian `affected`/`fix_deferred`), so there is nothing to upgrade to.
- Every one needs local privileged operations (mount, namespaces, ACLs, systemd-homed), terminal handling or Perl, none of which the app performs. The app runs unprivileged, with no setuid binaries, behind HTTP only.
- Removing the packages is not safe: `util-linux`, `bsdutils`, `login`, `ncurses-bin` and `perl-base` are Essential or required in Debian, and purging them breaks `dpkg` and the base image contract.
- Alternatives considered and **not** done in this step: a distroless Python base (no shell, so `docker/entrypoint.sh` would need rewriting), or Alpine (musl builds of psycopg and pydantic-core). Both are larger changes with their own risks; candidates for later.

**Re-evaluation:** rebuild with `--pull` and rerun Trivy at least monthly, and whenever Debian publishes fixes for these CVEs (see [`ops/runbook.md`](../ops/runbook.md)). Every CD deploy rebuilds the image on Render; whether Render pulls a fresh base each time is not documented, so the manual rescan is the check.

## Limits of these scans

- **Semgrep `auto`** is a pattern scan, not data-flow analysis across functions. PR #1's F1 (trusting `X-Forwarded-For` via a uvicorn CLI flag in a shell script) was found by manual review, not by Semgrep.
- **pip-audit / npm audit / Trivy** see only *known, published* advisories. Trivy scanned the app image only; `postgres:16-alpine` (local Compose) and Render's managed PostgreSQL were not scanned. Trivy reports installed versions, not reachability (see S6).
- **gitleaks** checks git history only, not Render or GitHub settings. Secrets live only in Render environment variables and GitHub Actions secrets, which were never read.
- Only Semgrep runs on every PR (`ci.yml`). pip-audit, npm audit, gitleaks and Trivy were run manually for this report; adding them to CI is a possible follow-up, not done here.
