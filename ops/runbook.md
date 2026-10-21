# BenchTrack runbook

Day-to-day operations for local Docker Compose and production on Render (https://benchtrack.onrender.com). Setup details and deploy troubleshooting: [`docs/deployment.md`](../docs/deployment.md). Incidents: [`ops/incidents/`](incidents/).

> **Rules.** Never paste secrets (`STAFF_TOKEN`, `DATABASE_URL`, the deploy hook) into chats, issues or logs. Production changes need an explicit human "yes" for that action, and agents never merge to `main` ([AI policy](../security/ai-tool-data-policy.md)).

Commands are PowerShell (use `curl.exe`, not the `curl` alias).

## 1. Start and stop

### Local (Docker Compose)

```powershell
Copy-Item .env.example .env              # once; set STAFF_TOKEN (16+ chars)
docker compose up --build -d --wait      # build, migrate, wait until healthy
docker compose ps                        # both services "healthy"
docker compose stop                      # stop, keep containers and data
docker compose down                      # remove containers, keep the pgdata volume
```

- Port 8000 busy: `$env:APP_PORT = "8010"` before `up` (the app binds to `127.0.0.1` only).
- **`docker compose down -v` deletes the database volume.** Only do it on purpose.
- After editing `.env`: `docker compose up -d --force-recreate app` so the container picks it up.

### Production (Render)

- **Stop:** Render dashboard → web service → *Settings* → *Suspend Web Service*. **Resume** from the same place.
- **Restart without a new build:** web service → *Manual Deploy* → *Restart service*, or redeploy the current commit (see §4).
- The free instance also sleeps by itself after inactivity; the first request wakes it in about a minute (§7).

## 2. Health and version check

```powershell
curl.exe -s https://benchtrack.onrender.com/api/health
# {"status":"ok","database":"ok","version":"<full commit SHA>"}
git fetch origin; git rev-parse origin/main   # should equal "version"
curl.exe -s http://127.0.0.1:8000/api/health  # local (APP_PORT if changed)
```

| Response | Meaning | Next step |
|---|---|---|
| `200` with `status: ok` and the expected `version` | Healthy, right commit | none |
| `200` with an older `version`, or no `version` field | Stale deploy | Check the latest CD run ([deployment troubleshooting](../docs/deployment.md#deploy-troubleshooting), [incident 2026-10-21](incidents/2026-10-21-deploy-not-applied.md)) |
| `503` `{"status":"degraded","database":"error"}` | App up, database unreachable | Render → PostgreSQL status; free databases expire (§7); check `DATABASE_URL` |
| No response for ~1 minute, then OK | Free instance waking up | none |
| Repeated failures or a 5xx page from the proxy | App not running | Render → *Events* and *Logs* (§3) |

## 3. Logs

App logs are JSON lines, one per event. Tracking codes appear masked as `BT-*****`, and secrets are never logged.

```powershell
docker compose logs -f app                         # follow
docker compose logs app --since 10m
docker compose logs app | Select-String '"level": "ERROR"'
docker compose logs db
```

- **Render:** web service → *Logs* (live tail, search). Build output is under *Events* → the deploy.
- **At startup, look for:** `benchtrack: applying database migrations`, the Alembic lines, `Uvicorn running on http://0.0.0.0:<PORT>`. A `CLIENT_IP_HEADER` warning means the public rate limit is misconfigured ([deployment](../docs/deployment.md)).
- **CI/CD:** GitHub → *Actions*, or `gh run list`, `gh run view <id> --log`.

## 4. Deploy and rollback

### Normal deploy (CI/CD)

1. Merge to `main` (a human merges).
2. **CI** runs 6 jobs. If it succeeds, **CD** calls the Render deploy hook and polls `/api/health` until `version` equals the merged commit (up to ~10 min).
3. CD summary: `✅ Deployed <sha>` means done. `⚠️ NOT DEPLOYED` means the hook secret is missing; `❌ Deploy NOT verified` means look at Render *Events*/*Logs*. See [troubleshooting](../docs/deployment.md#deploy-troubleshooting).

```powershell
gh run list --limit 4
gh run watch <cd-run-id> --exit-status
```

Re-deploy the latest `main` without a new commit: Actions → the latest **CD** run → *Re-run all jobs* (needs approval if an agent does it).

### Manual rollback (bad deploy)

1. Render dashboard → web service → **Deploys** (*Events*) → pick the last good deploy → **redeploy that previous commit** (*Rollback*).
2. Verify: `curl.exe -s https://benchtrack.onrender.com/api/health` → `version` is the old commit SHA.
3. **Fix forward on `main`** (e.g. `git revert <bad sha>` in a PR, merged by a human). CD then deploys and verifies the fix. Until then, `main` and production differ; that is expected and visible in `version`.
4. Record it in `ops/incidents/`.

**Database caveat:** a rollback does **not** undo migrations. The entrypoint only runs `alembic upgrade head`, so the old code runs against the newer schema. Migrations must stay backward compatible for one release (add columns and tables; drop them only in a later release). If a migration itself is the problem, stop and plan a downgrade manually; never run `alembic downgrade` against production without a backup.

## 5. Seeding (fictional demo data only)

The seed is idempotent and contains only fictional data (`+506 0000-xxxx` phones, `example.com` emails, codes `BT-DEM..`).

```powershell
docker compose exec app python -m app.seed      # local Compose
```

**Production** (from the maintainer's machine, using the database's **External** URL; never commit or paste it):

```powershell
cd backend
$env:DATABASE_URL = "<External Database URL>"
uv run python -m app.seed
Remove-Item Env:DATABASE_URL
```

Migrations already run on every deploy; seeding is optional. Expected output: `Seed complete: N customers and M tickets added.` (0 and 0 on re-runs).

## 6. Rotate `STAFF_TOKEN`

Rotate it when it may have been exposed (chat, screenshot, log, commit) or when someone loses access. The old token stops working as soon as the app restarts.

1. Generate a new value locally (don't paste it anywhere else):
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Production:** Render → web service → *Environment* → edit `STAFF_TOKEN` → save and deploy, which restarts the service with the new value.
3. Verify: `curl.exe -s https://benchtrack.onrender.com/api/health` → `status: ok` and the **same** `version` (only the env changed). Staff sessions with the old token get `401`; the app clears the stored token and shows *Invalid or expired token*. Sign in with the new token.
4. **Local:** update `.env`, then `docker compose up -d --force-recreate app`.
5. If it was exposed, add a short note to `ops/incidents/` (what was exposed, when it was rotated). Production and local tokens must always differ.

The app refuses to start if `STAFF_TOKEN` is missing or shorter than 16 characters. If Render shows the service failing right after step 2, check the value's length (it is never printed in logs).

## 7. Free-tier limits (Render)

| Limit | Effect | What to do |
|---|---|---|
| Web service sleeps after inactivity (about 15 min) | First request takes about a minute | Expected; CD's 10-minute wait covers it |
| **Free PostgreSQL expires about 30 days after creation** | `/api/health` → `503 degraded`; data is lost | Put the expiry date in a calendar. Before it, back up or upgrade; after it, create a new database, update `DATABASE_URL`, redeploy (migrations run), re-seed |
| Slow builds (several minutes) | Deploys take a while | CD waits up to ~10 minutes |
| Small RAM/CPU | Fine for one shop | No load tests against production |

Details: [`docs/deployment.md`](../docs/deployment.md#free-tier-limits).

## 8. Routine checks

- **Monthly:** rebuild with the latest base images and rerun the scans (`docker compose build --pull app`, then Trivy, pip-audit, npm audit, gitleaks). Triage in [`security/scan-findings.md`](../security/scan-findings.md).
- **Before the free database's expiry date:** back up or replace it (§7).
- **After every deploy:** `version` in `/api/health` matches `origin/main` (§2).
