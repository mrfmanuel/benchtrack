#!/usr/bin/env python3
"""Synthetic uptime check of the user-facing journeys, with alert issues (issue #7).

    python scripts/uptime_check.py --base-url https://benchtrack.onrender.com
    python scripts/uptime_check.py --simulate-failure          # base URL from $APP_URL
    python scripts/uptime_check.py --report-issue              # CI: open/comment/close alert issue

Checks what a customer and the shop actually hit, without any token:
  1. GET /api/health                → 200, status "ok", database "ok"
  2. GET /track/BT-DEM22            → 200 HTML (the SPA serves the tracking page)
  3. GET /api/public/track/BT-DEM22 → 200 JSON with exactly the public whitelist fields
With --simulate-failure it also checks a path that doesn't exist (a 404), so the alert can be
demonstrated without touching production.

Connection errors, timeouts and 5xx are retried for up to RETRY_BUDGET seconds (a free Render
instance takes about a minute to wake up); other wrong answers fail at once. Exit code 1 if
any check failed. With --report-issue (needs `gh` and GH_TOKEN with issues: write) a failure
opens one issue labelled `alert`, or comments on the open one; a success comments the recovery
and closes it. Only status codes, timings and public URLs are reported: no token is used and
no customer data is fetched. Stdlib only. Details: ops/alerting.md.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

DEMO_CODE = "BT-DEM22"  # fictional seed ticket, also the README's live-demo link
PUBLIC_FIELDS = {  # openapi.yaml PublicTracking (spec §9.15)
    "tracking_code",
    "device_type",
    "brand",
    "model",
    "status",
    "last_status_change_at",
    "timeline",
}
SIMULATED_PATH = "/api/uptime-check-simulated-failure"
REQUEST_TIMEOUT = 30  # seconds per request
RETRY_BUDGET = 90  # seconds per check for transient failures (cold start)
RETRY_INTERVAL = 10
SLOW_MS = 5000  # reported as "slow" in the summary (not an alert on its own)
ALERT_LABEL = "alert"
ALERT_TITLE_PREFIX = "Uptime alert:"
MARKER = "<!-- uptime-check -->"


@dataclass
class Response:
    status: int
    content_type: str
    body: bytes
    latency_ms: int


@dataclass
class Check:
    name: str
    path: str
    validate: Callable[[Response], str | None]  # None = OK, else the reason
    retry: bool = True


@dataclass
class Result:
    name: str
    url: str
    ok: bool
    status: int | None = None
    latency_ms: int | None = None
    detail: str = ""
    attempts: int = 0
    extra: dict = field(default_factory=dict)


# --- What "working" means for each journey ----------------------------------------------


def _json(response: Response) -> object | None:
    try:
        return json.loads(response.body)
    except ValueError:
        return None


def validate_health(response: Response) -> str | None:
    if response.status != 200:
        return f"expected HTTP 200, got {response.status}"
    body = _json(response)
    if not isinstance(body, dict):
        return "response is not a JSON object"
    if body.get("status") != "ok" or body.get("database") != "ok":
        return f"status={body.get('status')!r}, database={body.get('database')!r}"
    return None


def validate_tracking_page(response: Response) -> str | None:
    if response.status != 200:
        return f"expected HTTP 200, got {response.status}"
    if "text/html" not in response.content_type:
        return f"expected HTML, got {response.content_type or 'no content type'}"
    return None


def validate_tracking_api(response: Response) -> str | None:
    if response.status != 200:
        return f"expected HTTP 200, got {response.status}"
    body = _json(response)
    if not isinstance(body, dict):
        return "response is not a JSON object"
    if set(body) != PUBLIC_FIELDS:
        # Field names only: never echo values from the response.
        extra, missing = sorted(set(body) - PUBLIC_FIELDS), sorted(PUBLIC_FIELDS - set(body))
        return f"fields differ from the public whitelist (extra: {extra}, missing: {missing})"
    if body.get("tracking_code") != DEMO_CODE:
        return "returned a different tracking code"
    return None


def checks(simulate_failure: bool) -> list[Check]:
    result = [
        Check("Health (app + database)", "/api/health", validate_health),
        Check("Tracking page (SPA)", f"/track/{DEMO_CODE}", validate_tracking_page),
        Check(
            "Tracking lookup (public API)", f"/api/public/track/{DEMO_CODE}", validate_tracking_api
        ),
    ]
    if simulate_failure:
        result.append(
            Check("Simulated failure (test only)", SIMULATED_PATH, validate_health, retry=False)
        )
    return result


# --- HTTP and retries ----------------------------------------------------------------------


def fetch(url: str, timeout: float = REQUEST_TIMEOUT) -> Response:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"unsupported URL: {url}")
    connection_class = (
        http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_class(parts.hostname, parts.port, timeout=timeout)
    path = parts.path or "/"
    started = time.monotonic()
    try:
        connection.request(
            "GET", path, headers={"User-Agent": "benchtrack-uptime-check", "Accept": "*/*"}
        )
        reply = connection.getresponse()
        body = reply.read(1_000_000)
        latency = int((time.monotonic() - started) * 1000)
        return Response(reply.status, reply.getheader("Content-Type", ""), body, latency)
    finally:
        connection.close()


def run_check(
    check: Check,
    base_url: str,
    fetcher: Callable[[str], Response] = fetch,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    budget: float = RETRY_BUDGET,
    interval: float = RETRY_INTERVAL,
) -> Result:
    url = base_url.rstrip("/") + check.path
    started = clock()
    attempts = 0
    while True:
        attempts += 1
        try:
            response = fetcher(url)
        except (OSError, http.client.HTTPException) as exc:  # includes timeouts
            transient, status, latency = True, None, None
            reason = f"request failed: {type(exc).__name__}"
        else:
            status, latency = response.status, response.latency_ms
            transient = response.status >= 500
            reason = check.validate(response)
            if reason is None:
                return Result(check.name, url, True, status, latency, "", attempts)
        if not (check.retry and transient) or clock() - started + interval > budget:
            return Result(check.name, url, False, status, latency, reason or "", attempts)
        sleep(interval)


def run_all(base_url: str, simulate_failure: bool, **kwargs) -> list[Result]:
    return [run_check(check, base_url, **kwargs) for check in checks(simulate_failure)]


# --- Reporting -------------------------------------------------------------------------------


def summary_markdown(results: list[Result], run_url: str | None, now: datetime) -> str:
    failed = [r for r in results if not r.ok]
    head = (
        f"**{len(failed)} of {len(results)} checks failed**"
        if failed
        else f"**All {len(results)} checks passed**"
    )
    lines = [
        MARKER,
        f"{head} at {now.strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "| Check | Result | HTTP | Latency | Attempts | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        latency = "—" if r.latency_ms is None else f"{r.latency_ms} ms"
        if r.latency_ms is not None and r.latency_ms > SLOW_MS:
            latency += " (slow)"
        lines.append(
            f"| [{r.name}]({r.url}) | {'✅ OK' if r.ok else '❌ FAIL'} | {r.status or '—'} "
            f"| {latency} | {r.attempts} | {r.detail or '—'} |"
        )
    if run_url:
        lines += ["", f"Run: {run_url}"]
    lines += ["", f"What to do: [ops/alerting.md]({docs_url()})."]
    return "\n".join(lines)


def docs_url() -> str:
    """Absolute link to the response steps (works in issues and in the Actions summary)."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "mrfmanuel/benchtrack")
    return f"{server}/{repo}/blob/main/ops/alerting.md#how-to-respond"


Gh = Callable[[list[str]], str]


def run_gh(args: list[str]) -> str:
    gh = shutil.which("gh")
    if gh is None:
        raise RuntimeError("`gh` not found on PATH (needed for --report-issue).")
    # Fixed `gh` sub-commands built in this module; titles and bodies are passed as arguments,
    # never through a shell.
    completed = subprocess.run(  # noqa: S603
        [gh, *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return completed.stdout


def find_open_alert(gh: Gh) -> int | None:
    issues = json.loads(
        gh(
            [
                "issue",
                "list",
                "--label",
                ALERT_LABEL,
                "--state",
                "open",
                "--json",
                "number,title",
                "--limit",
                "100",
            ]
        )
    )
    numbers = [i["number"] for i in issues if i["title"].startswith(ALERT_TITLE_PREFIX)]
    return min(numbers) if numbers else None


def report_issue(results: list[Result], summary: str, gh: Gh = run_gh) -> str:
    """Open, comment on or close the alert issue. Returns what was done."""
    failed = [r.name for r in results if not r.ok]
    open_issue = find_open_alert(gh)
    if failed:
        if open_issue is not None:
            gh(["issue", "comment", str(open_issue), "--body", "Still failing.\n\n" + summary])
            return f"commented on #{open_issue} (still failing)"
        title = f"{ALERT_TITLE_PREFIX} {', '.join(failed)} failing"
        url = gh(
            ["issue", "create", "--label", ALERT_LABEL, "--title", title, "--body", summary]
        ).strip()
        return f"opened {url}"
    if open_issue is not None:
        gh(["issue", "comment", str(open_issue), "--body", "Recovered.\n\n" + summary])
        gh(["issue", "close", str(open_issue), "--reason", "completed"])
        return f"closed #{open_issue} (recovered)"
    return "no alert open, nothing to do"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("APP_URL", ""))
    parser.add_argument("--simulate-failure", action="store_true")
    parser.add_argument("--report-issue", action="store_true")
    parser.add_argument("--run-url", default=os.environ.get("RUN_URL"))
    args = parser.parse_args(argv)
    if not args.base_url:
        print("No base URL: pass --base-url or set APP_URL.", file=sys.stderr)
        return 2

    results = run_all(args.base_url, args.simulate_failure)
    summary = summary_markdown(results, args.run_url, datetime.now(UTC))
    print(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")
    if args.report_issue:
        print(f"\nAlert issue: {report_issue(results, summary)}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
