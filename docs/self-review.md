# Self-review against the course rubric

A strict peer review of BenchTrack as of 2026-10-21 (branch `docs/final-readme`). Every score cites the files that prove it; where the evidence is weak, the score says so.

## Which rubric

The request was to use "the 14 criteria" of [`project/README.md`](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp/blob/main/project/README.md) in DataTalksClub/ai-dev-tools-zoomcamp. That file changed on **2026-10-16** (commit `3ef6f18`, "Revise project criteria and scoring"):

- **Current rubric:** 12 criteria, 24 points, **10 to pass**. It adds a task tracker, an agent team, observability, alerting and an on-call agent. Peer reviewers will use this one.
- **Previous draft:** the 14 criteria the request referred to (AI workflow, technologies, frontend, API contract, backend, database, …, agent extension pack, security, reproducibility), plus the list of expected repository paths.

Both are scored below, the current one first. The draft text comes from the removed lines of `3ef6f18`. For a few draft criteria only some score levels survive in that diff, so the scores use the levels that are shown.

## Summary

| Rubric | Score | Pass mark |
|---|---|---|
| **Current (12 criteria)** | **18 / 24** (16 before the quick fixes in this PR) | 10 |
| Previous draft (14 criteria) | 30 / 30 | — |

The current rubric costs points where the project has no artifacts at all: a public task tracker, metrics and traces, alerting, an on-call agent, and a separate dev environment with manual promotion. None of these is a quick fix; see [Open gaps](#open-gaps).

## Current rubric (12 criteria, 24 points)

| # | Criterion | Score | Evidence | Why not more |
|---|---|---|---|---|
| 1 | Problem description | **2 / 2** | [`README.md`](../README.md) "Problem and solution", "Features", "Live demo"; [`product-spec.md`](../product-spec.md) §1–4 | — |
| 2 | Product specification | **1 / 2** | [`product-spec.md`](../product-spec.md): features, non-functional requirements, out of scope, **acceptance scenarios (§8)**, 27 decisions (§9) | **No public task tracker.** The repo has 0 GitHub issues; tasks live in the AI log and PRs, which have no acceptance criteria per task and no tracker the agents read from. |
| 3 | Agent team specification | **2 / 2** | [`docs/agent-team.md`](agent-team.md): members, responsibilities, limits, hand-offs and the rules that came from real events. Backed by [`security/agent-security-notes.md`](../security/agent-security-notes.md) and [`docs/permissions.md`](permissions.md) | Written down in this PR, after the work. A reviewer could see it as documenting the process rather than defining it upfront, but the AI log shows the same process step by step. (1 before this PR: the roles were scattered.) |
| 4 | Context management | **2 / 2** | [`AGENTS.md`](../AGENTS.md) (with [`CLAUDE.md`](../CLAUDE.md) pointing to it) links to the spec, the contract, `docs/database.md`, `docs/testing.md`, `docs/permissions.md`, `docs/agent-team.md`, `docs/architecture.md`, `ops/runbook.md`, `security/README.md` | — |
| 5 | Application | **2 / 2** | React SPA → FastAPI → PostgreSQL ([`docs/architecture.md`](architecture.md)); `docker compose up --build -d --wait` starts everything; the data persists in the `pgdata` volume (checked in Step 5: restart kept 7 customers and 12 tickets); [screenshots](screenshots/) and the live demo | One manual step before the command: set `STAFF_TOKEN` in `.env` (the app refuses a default token on purpose). |
| 6 | Testing | **2 / 2** | Unit (`backend/tests/unit`, 285; Vitest 136), API (264) and integration on real PostgreSQL (`backend/tests/integration`, 10). **One command:** `uv run --no-project python scripts/test_all.py` → all suites PASS, including 559 backend tests in one pytest run ([`docs/testing.md`](testing.md)) | (1 before this PR: integration needed a separate command and an environment variable.) |
| 7 | Containerization | **2 / 2** | [`Dockerfile`](../Dockerfile) (multi-stage, non-root), [`docker-compose.yml`](../docker-compose.yml) with `db` + `app`, health checks, migrations on start; `docker compose up --build -d --wait` | — |
| 8 | Deployment | **2 / 2** | https://benchtrack.onrender.com; `/api/health` reports the deployed commit (`3eb9052…` on 2026-10-21); public tracking https://benchtrack.onrender.com/track/BT-DEM22 → 200; [`docs/deployment.md`](deployment.md) | — |
| 9 | CI/CD | **2 / 3** | [`ci.yml`](../.github/workflows/ci.yml) (7 jobs on every PR and push), [`cd.yml`](../.github/workflows/cd.yml) deploys after green CI and verifies the version; required checks via the `protect-main` ruleset; rollback in [`ops/runbook.md`](../ops/runbook.md) §4 | **No dev/staging environment and no manual production gate.** CD deploys straight to production. |
| 10 | Observability | **1 / 2** | JSON logs with masked tracking codes (`app/logging_config.py`, `services/log_masking.py`), `/api/health` with DB check and version | **No metrics, no traces, no request/trace ID** that ties log lines of one request together, and no telemetry UI. |
| 11 | Alerting on user impact | **0 / 1** | — | No alert. CD warns on a failed deploy, but nothing watches users' experience (e.g. failing tracking lookups or 5xx rate). |
| 12 | On-call agent | **0 / 2** | — | No agent is woken by an alert. The incident in [`ops/incidents/`](../ops/incidents/2026-10-21-deploy-not-applied.md) was diagnosed by an agent, but it was started by a human, not by an alert. |
| | **Total** | **18 / 24** | | |

## Previous draft rubric (14 criteria, 30 points)

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 1 | Problem description | 2 / 2 | README "Problem and solution", spec §1–3 |
| 2 | AI-assisted development workflow | 2 / 2 | [`docs/ai-workflow.md`](ai-workflow.md): every step has the prompt, what was delegated, the human's manual review and the verification commands with outputs; context files listed; [`docs/agent-team.md`](agent-team.md) |
| 3 | Technologies and system architecture | 2 / 2 | README "Architecture" (Mermaid + tech table with roles); [`docs/architecture.md`](architecture.md): request paths, layers, data model, containers, CI/CD sequence, Render (new in this PR) |
| 4 | Frontend implementation | 3 / 3 | All HTTP in [`frontend/src/api/client.ts`](../frontend/src/api/client.ts), typed by `types.ts`; pages/components/lib split; 136 Vitest tests in 11 files (client, lib, pages, components); commands in README and `docs/testing.md` |
| 5 | API contract | 2 / 2 | [`openapi.yaml`](../openapi.yaml) written before the backend, Redocly lint in CI, parity tests (`backend/tests/api/test_contract.py`), Swagger UI from the file; `contract-reviewer` run: "Contract drift: none found" ([evidence](agent-extension-pack.md#7-contract-reviewer-by-name-without-the-plugin-after-the-drift-fixes)) |
| 6 | Backend implementation | 3 / 3 | Routers / services / schemas / models split ([`docs/architecture.md`](architecture.md) §3); 549 unit + API tests, 10 integration |
| 7 | Database integration | 2 / 2 | SQLAlchemy 2 + Alembic; SQLite (tests, quick dev) and PostgreSQL (integration, Compose, production); [`docs/database.md`](database.md) with environments, migrations, ER diagram, engine differences |
| 8 | Containerization | 2 / 2 | Dockerfile + Compose, README quick start |
| 9 | Integration testing | 2 / 2 | `backend/tests/integration/` behind the `integration` marker (separate from unit/API), real PostgreSQL migrations + HTTP workflows; CI job fails if any test is skipped; documented in `docs/testing.md` |
| 10 | Deployment | 2 / 2 | Live URL + version check |
| 11 | CI/CD pipeline | 2 / 2 | Tests on every PR, deploy after green CI on `main` |
| 12 | Agent extension pack | 2 / 2 | `AGENTS.md`; skills `contract-first-endpoint`, `release-check`; subagent `contract-reviewer`; read-only MCP server; guard + ruff hooks; plugin; [`docs/agent-extension-pack.md`](agent-extension-pack.md) with live evidence; [`docs/permissions.md`](permissions.md) |
| 13 | Security, audit and DevOps hardening | 2 / 2 | PR audit [`security/pr-audit-1.md`](../security/pr-audit-1.md) (real High finding fixed and verified in production); deterministic scans [`security/scan-findings.md`](../security/scan-findings.md) + raw outputs in `security/scans/`; [`security/agent-security-notes.md`](../security/agent-security-notes.md); operational diagnosis [`ops/incidents/2026-10-21-deploy-not-applied.md`](../ops/incidents/2026-10-21-deploy-not-applied.md); [`security/ai-tool-data-policy.md`](../security/ai-tool-data-policy.md) |
| 14 | Reproducibility | 2 / 2 | README: Compose quick start, local dev, configuration, tests (one command), CI/CD; `docs/deployment.md` for Render; commands written to work in PowerShell and POSIX shells |
| | **Total** | **30 / 30** | |

### Expected repository contents (draft list)

All present and tracked in git (checked with `git ls-files` on this branch):

| Path | | Path | |
|---|---|---|---|
| `README.md` | ✅ | `security/` | ✅ |
| `product-spec.md` | ✅ | `ops/` | ✅ |
| `AGENTS.md` | ✅ | `agent-capabilities/` | ✅ |
| `frontend/` | ✅ | `agent-hooks/` | ✅ |
| `backend/` | ✅ | `mcp-server/` | ✅ |
| `openapi.yaml` | ✅ | `plugins/` | ✅ |
| `docker-compose.yml` | ✅ | `docs/agent-extension-pack.md` | ✅ |
| `.github/workflows/` | ✅ | `docs/permissions.md` | ✅ |
| `docs/` | ✅ | | |

## Gaps fixed in this PR

| Gap | Fix |
|---|---|
| Integration tests needed their own command and environment variable | [`scripts/test_all.py`](../scripts/test_all.py): every suite with one cross-platform command (Compose PostgreSQL started for you), summary and exit code |
| No single description of the agent team and its process | [`docs/agent-team.md`](agent-team.md), linked from `AGENTS.md` and the README |
| No architecture document | [`docs/architecture.md`](architecture.md) |
| README written for a work in progress ("production deployment comes next") | Rewritten for a reviewer: live demo, screenshots, features, architecture, cross-platform commands, limitations |
| `docs/deployment.md` and `ops/runbook.md` still said CI has 6 jobs | 7 |
| `scripts/` and `plugins/tests/` weren't linted in CI | The agent-pack job's ruff step now covers `plugins/` and `scripts/` |

## Open gaps

Ordered by points per hour of work. Each needs a decision from the maintainer.

| Gap | Rubric points | Suggested fix |
|---|---|---|
| No alert on user impact | +1 | A synthetic check every few minutes: tracking lookup of a demo code plus `/api/health`, run by GitHub Actions `schedule` or an external uptime monitor. It notifies when lookups fail or are slow. On Render's free tier this also keeps the instance awake. |
| No public task tracker | +1 | GitHub Issues (or a Project) with one issue per task and acceptance criteria. Agents reference the issue in branch, commit and PR. This only counts going forward; past work can't be backfilled honestly. |
| Observability is logs only | +1 | A request ID middleware (in every log line and a response header), OpenTelemetry traces and metrics for the tracking and ticket journeys, exported to a free hosted UI. Customer data and tokens are scrubbed before export. |
| No on-call agent | +2 | The alert triggers a workflow that starts a read-only diagnosing agent (health, logs, recent deploys), posts its findings to an issue, and proposes a fix as a PR. A human approves, as in [`docs/agent-team.md`](agent-team.md). |
| No dev/staging + manual production deploy | +1 | A second Render service for `main` (dev) and a GitHub `production` environment with a required reviewer for the production deploy job. |

Product issues found while reviewing (not rubric items):
- **Public progress stepper:** it shows skipped steps as done (BT-DEM28 never waited for parts but "Waiting for parts" is filled; see [`screenshots/tracking.png`](screenshots/tracking.png)). The history list is correct. Small frontend fix; listed in the README's known limitations.
- **Receipt screenshot:** the tracking URL on the receipt is the local `http://127.0.0.1:8010/...`, because it uses the page's origin. Correct behaviour, just less illustrative than the production URL.
