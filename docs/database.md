# Database

BenchTrack uses SQLAlchemy 2.x with engine-agnostic models (`backend/app/models.py`). SQLite is used where speed and zero setup matter; PostgreSQL wherever the app really runs. The schema is owned by **Alembic** — the app never creates tables itself.

## Environments

| Environment | Database | Configured by | Schema created by |
|---|---|---|---|
| Unit tests (`tests/unit/`) | none | — | — |
| API tests (`tests/api/`) | SQLite in-memory (`sqlite://`, `StaticPool`) | test fixture (fixed) | `Base.metadata.create_all` in the fixture |
| Local development | SQLite file (`sqlite:///./benchtrack.db`, relative to `backend/`) **or** Compose PostgreSQL | `DATABASE_URL` in `.env` | `uv run alembic upgrade head` |
| Integration tests (`tests/integration/`) | Compose PostgreSQL, database `benchtrack_test` | `TEST_DATABASE_URL` (env or `.env`) | Alembic, per test, on an empty schema |
| Docker Compose (Step 5) and production | PostgreSQL | `DATABASE_URL` | `alembic upgrade head` at container start |

`tests/api/test_schema.py` also runs the migrations on a temporary SQLite file and checks they match the models, so migration drift is caught even without PostgreSQL.

## Configuration

| Variable | Used by | Example |
|---|---|---|
| `DATABASE_URL` | app, Alembic, seed | `sqlite:///./benchtrack.db` · `postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack` |
| `TEST_DATABASE_URL` | integration tests only | `postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT` | `docker-compose.yml` | `benchtrack` / `benchtrack` / `benchtrack` / `5433` |

- `postgres://` and `postgresql://` URLs (as handed out by hosting platforms) are rewritten to `postgresql+psycopg://` (psycopg 3) by `app.config.normalize_database_url`, for the app and Alembic alike.
- Alembic and the seed script only need `DATABASE_URL` (`DatabaseSettings`); the app additionally needs `STAFF_TOKEN`.
- **Use `127.0.0.1`, not `localhost`**, for the Compose database on Windows: `localhost` resolves to IPv6 `::1` first, the container is published on IPv4 loopback only, and every new connection waits for the IPv6 attempt to time out.
- PostgreSQL connections use `connect_timeout=5`, so `/api/health` returns `503` within ~5 s when the database is unreachable instead of hanging.

## Local PostgreSQL (Docker Compose)

```powershell
docker compose up -d db --wait      # postgres:16-alpine on 127.0.0.1:5433, named volume pgdata
docker compose ps                   # STATUS should be "healthy" (pg_isready)
docker compose stop db              # keep data
docker compose down -v              # remove container AND data volume (destructive)
```

## Migrations

All commands run from `backend/`.

```powershell
uv run alembic upgrade head                              # apply all migrations
uv run alembic current                                   # show applied revision
uv run alembic downgrade -1                              # roll back one revision
uv run alembic revision --autogenerate -m "add x to y"   # after changing app/models.py
```

Rules for schema changes:

1. Change `app/models.py`, then autogenerate a revision and **review it by hand** (autogenerate misses renames and data migrations).
2. Constraint and index names come from the naming convention in `app/db.py` (`pk_`, `uq_`, `fk_`, `ix_`), so they are identical on SQLite and PostgreSQL and can be referenced in later migrations.
3. `render_as_batch=True` lets the same migration alter tables on SQLite.
4. Run `uv run pytest` (SQLite drift check) and `uv run pytest -m integration` (PostgreSQL upgrade, no-diff, downgrade/upgrade) before committing.

## Seeding

```powershell
uv run alembic upgrade head
uv run python -m app.seed     # idempotent: re-running adds nothing
```

Adds 6 fictional customers and 12 tickets covering all statuses, with 3 open tickets idle for more than 7 days (stale on the dashboard). Seeded tracking codes are fixed (`BT-DEM22`…`BT-DEM2D`) so re-runs can skip them — they are predictable, so **never seed a production database**. The script refuses to run if the schema is missing.

## Integration tests

```powershell
docker compose up -d db --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test"
cd backend
uv run pytest -m integration
```

- Without `TEST_DATABASE_URL` (or with a non-PostgreSQL URL) the tests are **skipped** with a message.
- Every test **drops and recreates the `public` schema**, so the run is refused unless the database name ends in `_test`. The database is created if missing.
- The default `uv run pytest` runs unit + API tests only (`-m 'not integration'` in `pyproject.toml`).

## Known differences between SQLite and PostgreSQL

| Topic | SQLite | PostgreSQL |
|---|---|---|
| Case-insensitive search (`q`) | `lower()` folds ASCII only: `JIMÉNEZ` does not match `Jiménez` | full Unicode (`ILIKE`) |
| Timestamps | stored naive; returned as UTC by `UTCDateTime` | `timestamp without time zone`, UTC by convention |
| `Numeric(10,2)` | stored as REAL | exact `numeric(10,2)` |

These only affect local development on SQLite; behaviour that matters is covered by the integration tests on PostgreSQL.

## Entity-relationship diagram

```mermaid
erDiagram
    customers ||--o{ tickets : "has"
    tickets ||--o{ ticket_events : "timeline"

    customers {
        int id PK
        varchar(100) name "indexed"
        varchar(20) phone UK "normalized, uq_customers_phone"
        varchar(254) email "nullable"
        timestamp created_at "UTC"
    }

    tickets {
        int id PK
        int customer_id FK "immutable, indexed"
        varchar(20) device_type "laptop|desktop|phone|tablet|printer|other"
        varchar(60) brand
        varchar(60) model "nullable"
        varchar(60) serial_number "nullable"
        varchar(2000) reported_issue
        varchar(2000) diagnosis "nullable"
        numeric estimated_cost "numeric(10,2), nullable, CRC"
        varchar(20) status "indexed"
        varchar(8) tracking_code UK "BT-XXXXX, uq_tickets_tracking_code"
        timestamp created_at "UTC, indexed"
        timestamp updated_at "UTC, indexed, stale detection"
    }

    ticket_events {
        int id PK
        int ticket_id FK "indexed"
        varchar(10) kind "status|note"
        varchar(20) from_status "nullable (initial event, notes)"
        varchar(20) to_status "nullable (notes)"
        varchar(1000) note "nullable for status events"
        timestamp created_at "UTC"
    }
```
