# Deployment (Render)

Production runs on [Render](https://render.com): one **web service** built from the root `Dockerfile` (API + built SPA) and one **Render PostgreSQL** database. GitHub Actions deploys: `cd.yml` calls Render's deploy hook after CI passes on `main`, then waits until `/api/health` reports the deployed commit.

```
push to main ──► CI (ci.yml, 6 jobs) ──success──► CD (cd.yml) ──POST deploy hook──► Render builds Dockerfile
                                                     │                                   │
                                                     └── polls APP_URL/api/health ◄──────┘ entrypoint: alembic upgrade head → uvicorn
                                                         until version == commit SHA
```

## Render setup (one time)

### 1. PostgreSQL

*New → PostgreSQL*. Use the same region as the web service. Once it is available, copy its **Internal Database URL** for the web service; the External URL is only for connecting from your own machine.

### 2. Web service

*New → Web Service* → connect the GitHub repository:

| Setting | Value |
|---|---|
| Runtime / Language | **Docker** |
| Dockerfile path | `./Dockerfile` (build context: repo root) |
| Branch | `main` |
| Health check path | `/api/health` (returns `503` when the database is unreachable) |
| Auto-Deploy | **Off**: deploys come only from CD, after CI passes. With it on, Render would deploy every push, including commits whose CI fails. |

The container listens on `$PORT`, which Render sets itself. `docker/entrypoint.sh` runs `alembic upgrade head` before starting uvicorn, so migrations apply on every deploy. Uvicorn runs with `--no-proxy-headers`: the client IP for the rate limit comes from `CLIENT_IP_HEADER`, and HTTPS (for HSTS) from `X-Forwarded-Proto` (see [`security/pr-audit-*.md`](../security/)).

### 3. Environment variables (web service → Environment)

| Variable | Value | Notes |
|---|---|---|
| `STAFF_TOKEN` | a new random value, at least 16 characters (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) | Required: the app refuses to start without it. Use a production-only token, never the local one. |
| `DATABASE_URL` | the Render PostgreSQL **Internal Database URL** | `postgres://` and `postgresql://` URLs are accepted (switched to psycopg 3 automatically). |
| `LOG_FORMAT` | `json` | Tracking codes are masked in logs. |
| `LOG_LEVEL` | `INFO` | optional |
| `CLIENT_IP_HEADER` | `CF-Connecting-IP` | **Required on Render** for the public rate limit (10 lookups/min per client). Render is fronted by Cloudflare, which overwrites this header with the real client IP. Without it every client shares the proxy's address (the app logs a warning at startup). Never `X-Forwarded-For`: Render appends to it, so clients can forge it (rejected at startup). |
| `VITE_SHOP_NAME` | shop name for receipts and the header | optional. Render passes service variables to the Docker build, where the frontend build bakes the name into the bundle (public). |

Do **not** set `APP_VERSION` on Render: the app falls back to `RENDER_GIT_COMMIT`, which Render sets for each deploy, so `/api/health` reports the deployed commit SHA.

### 4. Deploy hook and GitHub configuration

1. Render: web service → *Settings → Deploy Hook* → copy the URL. **It is a secret**: anyone holding it can trigger deploys.
2. GitHub: *Settings → Secrets and variables → Actions*:
   - **Secret** `RENDER_DEPLOY_HOOK_URL` = the hook URL
   - **Variable** `APP_URL` = `https://<service>.onrender.com` (no trailing path)
3. **Then deploy.** Adding the secret does not trigger anything by itself. Open the latest CD run on `main` and choose *Re-run all jobs*, or push a commit. See [troubleshooting](#deploy-troubleshooting).

### 5. Seed (optional, fictional demo data)

From your machine, using the database's **External** URL (put it in `.env` or the shell, never in a commit):

```powershell
cd backend
$env:DATABASE_URL = "<External Database URL>"   # not printed, not committed
uv run python -m app.seed
Remove-Item Env:DATABASE_URL
```

The seed is idempotent and contains only fictional data. Migrations already ran during the deploy.

## Free-tier limits

Limits observed when this was written; check Render's current docs.

- **The web service sleeps after a period of inactivity** (about 15 minutes). The next request wakes it, which takes up to about a minute; the first `/api/health` or page load after idle is slow, not broken.
- **Free PostgreSQL databases expire about 30 days after creation**. After that the app answers `503 {"status":"degraded","database":"error"}`. Upgrade, or create a new database, update `DATABASE_URL`, redeploy (migrations run on start) and re-seed. Data in an expired free database is lost: back up anything you need first.
- **Builds are slow** (several minutes for the multi-stage image). CD therefore waits up to ~10 minutes for the new version.
- Limited RAM/CPU: fine for one shop, not for load tests.

## Verifying a deploy

```powershell
curl.exe -s https://<service>.onrender.com/api/health
# {"status":"ok","database":"ok","version":"<full commit SHA>"}
git rev-parse origin/main   # should match "version"
```

A successful CD run ends with the notice `<sha> is live at <APP_URL>` and the job summary `✅ Deployed <sha>`.

## Deploy troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| CD run is green but shows a **⚠️ NOT DEPLOYED** warning and job summary | `RENDER_DEPLOY_HOOK_URL` was not set when the run started. Skipping is intentional, so the run is green. | Add the secret (and `APP_URL`), then *Re-run all jobs* on that CD run. A new secret is **not** picked up retroactively. ([incident 2026-10-21](../ops/incidents/2026-10-21-deploy-not-applied.md)) |
| `/api/health` has **no `version`** field, or a version other than `origin/main` | Production runs an older build: CD skipped or failed, or a deploy is still in progress | Check the latest CD run on `main` (Actions → CD): annotation and summary. Re-run it once configured. |
| CD fails: `APP_URL missing` | Secret set, variable not | Add the `APP_URL` variable; re-run. |
| CD fails: `Render deploy hook was rejected (HTTP 4xx)` | Wrong or revoked hook URL | Copy the hook again from Render (or regenerate it) into the secret; re-run. The URL is never printed in logs. |
| CD fails: `Deploy NOT verified … within ~10 minutes` | The build failed or is still running on Render, the service is asleep and slow to wake, or a newer commit was deployed meanwhile | Check Render → *Events/Logs* for the build. If a newer commit is live, its own CD run verifies it. If the build is merely slow, re-run CD. |
| `/api/health` → `503 degraded` | Database unreachable or expired (free tier) | Render → PostgreSQL status. Check `DATABASE_URL` uses the Internal URL. |
| Service won't start; logs show a `STAFF_TOKEN` error | `STAFF_TOKEN` missing or shorter than 16 characters | Set it in Render → Environment (the value is never logged); redeploy. |
| First request takes ~1 minute | Free instance waking from sleep | Expected on the free tier. |
| Startup log: `Running on Render without CLIENT_IP_HEADER` | The env var is missing; all clients share one public rate limit, so customers may see "Too many lookups" | Set `CLIENT_IP_HEADER=CF-Connecting-IP` in Render → Environment. |
| Pushes deploy even when CI fails | Render *Auto-Deploy* is on | Turn Auto-Deploy **off**; CD is the deploy path. |

Logs: Render → web service → *Logs* (JSON lines, tracking codes shown as `BT-*****`).
