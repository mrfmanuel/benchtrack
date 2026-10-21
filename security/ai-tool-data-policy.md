# AI tool and data policy

Applies to everyone working on BenchTrack, human or agent. Effective 2026-10-21.

## 1. AI tools in use

| Tool | Used for | Access |
|---|---|---|
| **Claude Code CLI** (Windows, in the repo folder) | Implementation: code, tests, docs, scans, git commits and pushes, opening PRs | Working tree, local Docker, `gh` CLI as the maintainer; every command and edit approved interactively (default permission mode). See [agent security notes](agent-security-notes.md). |
| **Claude in the Cowork desktop app** | Planning and review; operating GitHub and Render web UIs via Claude in Chrome | Project folder via a Linux VM bridge; the maintainer's Chrome with logged-in GitHub and Render sessions |
| Claude in Chrome (from either agent) | Browser checks of the local app (UI smoke tests, CSP), GitHub Actions and Render dashboards | Whatever the browser profile is signed in to |

No other AI tools are approved for this project. Adding one requires updating this table.

## 2. Data

### Never send to AI tools

- **Real customer data:** names, phones, emails, device details or notes of real people. BenchTrack's seeds and tests use fictional data only (`+506 0000-xxxx`, `example.com`).
- **Production secrets:** the production `STAFF_TOKEN`, `DATABASE_URL` (internal or external), `RENDER_DEPLOY_HOOK_URL`, GitHub tokens, Render API keys. **Never paste them into chats**, prompts, issues or PR comments.
- **Screenshots or logs that show any of the above.** Example: a Swagger UI screenshot showed the local token, so it was kept out of the repo and not shared. Crop or redact first.

### Allowed

- The repository contents (code, docs, fictional seeds), public documentation, and CI logs (they never contain secret values).
- Names of secrets and variables, but not their values. For example, "is `RENDER_DEPLOY_HOOK_URL` set?" is answered from `gh secret list`, which shows names and dates only.
- The local development token, *only* as an environment variable read by tools, never printed. It must differ from production.

### Retention and sharing

AI conversations may be retained by the provider. **Treat every AI conversation as non-confidential**: anything typed, pasted or shown to an agent may be stored outside our control. If a secret is exposed in a conversation anyway, rotate it (see [`ops/runbook.md`](../ops/runbook.md#rotate-staff_token)) instead of assuming it is gone.

## 3. Human review

- **Before merge:** a human reviews every change to `main` (the diff, and the security audit when there is one) and **merges it themselves**. Agents may open PRs and comment; they do not merge. (The agent platform's classifier blocked an agent merge attempt on PR #1; that is now a rule.)
- **Before any production action** (deploy, CD re-run, Render setting, production probe, production seeding): the agent explains what it will do, and a human says "yes" in chat **for that specific action**. Diagnosis before that is read-only.
- **Deviations:** if an approved procedure has to change, the agent stops, says what and why, and documents it ([example: PR #1 audit, F3](pr-audit-1.md)).
- Every significant AI-assisted task is logged in [`docs/ai-workflow.md`](../docs/ai-workflow.md), with what was delegated and what a human reviewed.

## 4. How AI-generated code is verified

| Check | What it catches | Where |
|---|---|---|
| Tests in three backend layers plus frontend Vitest; must pass before a task counts as done | Behaviour regressions | [`docs/testing.md`](../docs/testing.md), CI |
| **Contract parity** (`test_contract.py`) and Redocly lint | Code that drifts from `openapi.yaml`; PII fields on public schemas | CI |
| **Semgrep** (`--config auto --error`) | Insecure code patterns | CI on every PR and push |
| Dependency, secret and image scans: pip-audit, npm audit, gitleaks, Trivy | Known-vulnerable packages, leaked secrets, base-image CVEs | [`scan-findings.md`](scan-findings.md) (manual, at least monthly) |
| **Security audits** of PRs | Logic flaws scanners miss (e.g. the forged `X-Forwarded-For` rate-limit bypass) | [`pr-audit-1.md`](pr-audit-1.md) |
| **Manual browser checks** | UI flows, CSP breakage, mobile layout | Recorded in the workflow log |
| Deploy verification | The live version is the commit that passed CI | CD polls `/api/health` `version` |

AI-written tests are reviewed like code: a test that cannot fail, or that a tool silently skips, is a defect (example: `TestClient` cannot reproduce proxy-header bugs, so CI checks the real container).

## 5. Dependencies

- **Every new dependency must be justified** (why it is needed, why not the standard library or an existing dependency) in the PR or commit message.
- **Official registries only:** PyPI via `uv add`, npm via `npm install`. No packages from URLs, git forks or unofficial mirrors. Check the exact name against typosquats before adding.
- Lockfiles (`uv.lock`, `package-lock.json`) are committed and installed with `uv sync --locked` / `npm ci`; never edit them by hand.
- New dependencies must pass pip-audit or npm audit before merge.

## 6. Secrets handling

- Secrets live only in `.env` (git-ignored, local), Render environment variables and GitHub Actions secrets. `.env.example` holds placeholders only.
- Never print, log or commit secrets. Workflows pass them via `env:`; the app hides `STAFF_TOKEN` in config errors and masks tracking codes in logs.
- `gitleaks` over the full history must stay clean.
- If a secret is exposed in a commit, log, screenshot or AI conversation, **rotate it immediately** ([runbook](../ops/runbook.md#rotate-staff_token)) and record it in `ops/incidents/`.
