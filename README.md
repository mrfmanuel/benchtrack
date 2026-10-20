# BenchTrack

A lightweight repair-ticket tracker for a single small computer-repair shop, with a protected staff area and a public tracking page.

> 🚧 Work in progress — setup and usage instructions will be added as the backend and frontend are built.

## Problem

Small independent computer-repair shops (one technician, a bench, a WhatsApp number) track repairs in notebooks, chat threads and memory. This causes three recurring problems:

1. **Lost context** — the technician forgets what was diagnosed, which parts were ordered, or what price was quoted.
2. **Constant "is it ready yet?" messages** — customers have no way to check status, so they call or message repeatedly.
3. **No overview** — it is hard to see at a glance which devices are waiting for parts, which are ready for pickup, and which have been sitting on the bench for too long.

## Solution

- **Staff area** (protected by a staff token): register customers and repair tickets, move tickets through a fixed status workflow, add notes, print a receipt with the tracking code, and see a dashboard of open and stale work.
- **Public tracking page** (no login, `/track`): a customer enters the tracking code from their receipt (e.g. `BT-7K3QX`) and sees the current status and a timeline — without any personal data, notes or costs.

See [`product-spec.md`](product-spec.md) for the full scope, including what is out of scope for v1.

## Configuration

Copy `.env.example` to `.env` (never commit `.env`).

| Variable | Description | Default |
|----------|-------------|---------|
| `STAFF_TOKEN` | Bearer token for staff endpoints. Required; the app refuses to start if it is shorter than 16 characters. | — |
| `DATABASE_URL` | SQLAlchemy URL. SQLite for local dev/tests, PostgreSQL in Compose/production. | `sqlite:///./benchtrack.db` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `LOG_FORMAT` | `text` or `json` (`json` in Compose/production) | `text` |

## Documentation

- [`product-spec.md`](product-spec.md) — product scope and behavior (source of truth)
- [`openapi.yaml`](openapi.yaml) — API contract
- [`AGENTS.md`](AGENTS.md) — instructions for coding agents and contributors
- [`docs/database.md`](docs/database.md) — database environments, migrations, seeding, ER diagram
- [`docs/ai-workflow.md`](docs/ai-workflow.md) — AI-assisted development log
