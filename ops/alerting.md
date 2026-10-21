# Alerting

BenchTrack has one alert: a **synthetic uptime check** that does what a customer does and opens a GitHub issue when that fails ([issue #7](https://github.com/mrfmanuel/benchtrack/issues/7)).

| | |
|---|---|
| Workflow | [`.github/workflows/uptime.yml`](../.github/workflows/uptime.yml): every 15 minutes, plus *Run workflow* by hand |
| Checker | [`scripts/uptime_check.py`](../scripts/uptime_check.py) (stdlib Python, tests in [`scripts/tests/test_uptime_check.py`](../scripts/tests/test_uptime_check.py)) |
| Target | `vars.APP_URL` (production, https://benchtrack.onrender.com), the same variable CD uses |
| Alert channel | An issue labelled **`alert`**, titled `Uptime alert: <checks> failing`. GitHub notifies the repository's watchers (by email or the GitHub app, depending on their notification settings). |
| Credentials | None. The staff token is never used; the job's `GITHUB_TOKEN` only has `contents: read, issues: write`. |

## What is alerted, and why it reflects user impact

The checks are the requests a real user's journey makes, from outside, through Cloudflare and Render, exactly as a browser would:

| # | Check | Passes when | User impact if it fails |
|---|---|---|---|
| 1 | `GET /api/health` | `200` and `{"status": "ok", "database": "ok"}` | The app or its database is down. Staff can't work, and customers can't track. |
| 2 | `GET /track/BT-DEM22` | `200` with an HTML page | The tracking page itself (the SPA) doesn't load. A customer following the receipt link sees an error. |
| 3 | `GET /api/public/track/BT-DEM22` | `200` JSON with **exactly** the 7 public whitelist fields, for that code | The lookup a customer makes fails or returns the wrong shape. If the response ever contains extra fields, that is also a **privacy** failure (spec §9.15), so it alerts too. Only field *names* are reported, never values. |

`BT-DEM22` is a fictional seed ticket, the same one as the README's live-demo link. The staff area isn't checked: that would need the staff token in GitHub, and checks 1 and 3 already exercise the same app and database.

## Thresholds

| Setting | Value | Why |
|---|---|---|
| Schedule | every 15 minutes (`*/15 * * * *`) | Detects an outage in ~15 minutes. GitHub can start scheduled runs a few minutes late. |
| Request timeout | 30 s | A single hung request can't block the job |
| Retries | connection errors, timeouts and `5xx`, every 10 s, for up to **90 s per check** | A free Render instance takes about a minute to wake up. Waking up is not an outage, a minute and a half of errors is. |
| Not retried | other wrong answers: `4xx`, a wrong body, wrong fields | Deterministic: retrying wouldn't change them |
| Alert condition | **any** check still failing after its retries, in one run | One failed run already means at least 90 s of failure for real users; no second run is needed |
| Slow | > 5 s is marked "(slow)" in the report | Shown, not alerted on its own (cold starts are expected on the free tier) |
| Recovery | the first run where all checks pass | Comments "Recovered" with the results and closes the issue |

There is at most one open uptime alert. While it is open, failing runs comment on it ("Still failing") instead of opening new issues. Issues labelled `alert` whose titles don't start with `Uptime alert:`, such as issue #7 itself, are never touched.

## How to test

**Locally**, read-only. Nothing is opened without `--report-issue`:

```bash
uv run --no-project python scripts/uptime_check.py --base-url https://benchtrack.onrender.com
uv run --no-project python scripts/uptime_check.py --base-url http://127.0.0.1:8000 --simulate-failure   # exit code 1
uv run --no-project python -m unittest discover -s scripts/tests                                        # unit tests (also in CI)
```

**End to end** (opens and closes a real alert issue, production is not changed):

1. *Actions → Uptime → Run workflow*, tick **simulate_failure**, run. The extra check requests `/api/uptime-check-simulated-failure`, which doesn't exist, gets `404` and fails. The run turns red and an `Uptime alert: Simulated failure (test only) failing` issue opens. With the CLI: `gh workflow run uptime.yml -f simulate_failure=true`.
2. *Run workflow* again without the box (or wait for the next scheduled run). All checks pass, and the issue gets a "Recovered" comment and is closed.

The demonstration runs are recorded under [Demonstration](#demonstration).

## How to respond

1. **Open the alert issue.** The table shows which check failed, the HTTP status, the latency, the number of attempts and the run link.
2. **Confirm the problem from outside:** `curl.exe -s https://benchtrack.onrender.com/api/health` (PowerShell) or `curl -s …` (Linux/macOS). Then open https://benchtrack.onrender.com/track/BT-DEM22 in a browser.
3. **Diagnose read-only** with the [runbook](runbook.md):

   | What the check shows | Likely cause | Where to look |
   |---|---|---|
   | No response or `502`/`503` for 90 s | Render instance down or crash-looping; a bad deploy | Render → service → *Events* / *Logs*; the last [CD run](https://github.com/mrfmanuel/benchtrack/actions/workflows/cd.yml) ([runbook §2–4](runbook.md#2-health-and-version-check)) |
   | `503` with `database: error` | Database unreachable or the free database expired | Render → PostgreSQL ([runbook §7](runbook.md#7-free-tier-limits-render)) |
   | Health OK, lookup `404` | Demo data missing, e.g. after a database was recreated | Re-seed ([runbook §5](runbook.md#5-seeding-fictional-demo-data-only)) |
   | Health OK, tracking page fails | SPA build or routing broken by a deploy | The last deploy's commit; roll back ([runbook §4](runbook.md#4-deploy-and-rollback)) |
   | Lookup has wrong fields | A regression in the public whitelist (privacy) | Roll back first, then fix on a branch with a test |

4. **Act only with approval.** Production changes (rollback, re-running CD, Render settings) need the maintainer's explicit "yes" ([agent team](../docs/agent-team.md)).
5. **Acknowledge** by commenting on the alert issue (who is on it, what was done). It closes itself on the first passing run. Closing it by hand is fine; if the check still fails, the next run opens a new issue.
6. **Silence it** during planned work: *Actions → Uptime → ⋯ → Disable workflow*, then enable it again afterwards. Say so in a comment on the open alert.

For a real incident, write it up in [`incidents/`](incidents/).

## Limits

- **It only sees what it checks.** These are three requests from one GitHub-hosted runner. A partial outage (one region, one browser, the staff pages) can be missed. There are no metrics behind it yet ([#10](https://github.com/mrfmanuel/benchtrack/issues/10)).
- **It depends on GitHub Actions.** If Actions is down or delays the schedule, alerts are late. GitHub also disables scheduled workflows in repositories with no activity for 60 days.
- **The notification is an issue.** There is no paging, SMS or on-call rotation; it relies on someone watching the repository.
- **Issues opened by `GITHUB_TOKEN` don't trigger other workflows.** A future on-call agent ([#9](https://github.com/mrfmanuel/benchtrack/issues/9)) that should start on `issues: opened` needs this job to open the issue with a GitHub App or another token, or needs to be called from this workflow directly.
- **Free tier:** a request every 15 minutes usually keeps the free Render instance awake (it sleeps after ~15 minutes idle), which uses most of the workspace's free instance hours (~750 h/month). A second free service, such as a dev environment ([#11](https://github.com/mrfmanuel/benchtrack/issues/11)), would not fit as well.
- **It needs the demo data.** If the production database is recreated without re-seeding, check 3 fails with `404` even though real tickets might work.

## Demonstration

Recorded after the workflow is merged (it can only be dispatched from `main`).
