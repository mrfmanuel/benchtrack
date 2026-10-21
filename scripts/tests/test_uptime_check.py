"""Tests for scripts/uptime_check.py: checks, retries, summary and the alert issue."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "uptime_check.py"
spec = importlib.util.spec_from_file_location("uptime_check", SCRIPT)
uc = importlib.util.module_from_spec(spec)
sys.modules["uptime_check"] = uc  # dataclasses need the module registered
spec.loader.exec_module(uc)

BASE = "https://benchtrack.example.com"
HEALTH = {"status": "ok", "database": "ok", "version": "abc"}
TRACKING = {
    "tracking_code": "BT-DEM22",
    "device_type": "laptop",
    "brand": "Lenovo",
    "model": "ThinkPad T14",
    "status": "received",
    "last_status_change_at": "2026-10-20T05:23:02Z",
    "timeline": [{"status": "received", "at": "2026-10-20T05:23:02Z"}],
}


def json_response(status, body, latency=120):
    return uc.Response(status, "application/json", json.dumps(body).encode(), latency)


def healthy_site(url):
    path = url.removeprefix(BASE)
    if path == "/api/health":
        return json_response(200, HEALTH)
    if path == "/track/BT-DEM22":
        return uc.Response(200, "text/html; charset=utf-8", b"<!doctype html>", 80)
    if path == "/api/public/track/BT-DEM22":
        return json_response(200, TRACKING)
    return json_response(404, {"error": {"code": "not_found", "message": "Not found."}})


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def run(fetcher, simulate=False, clock=None):
    clock = clock or FakeClock()
    return uc.run_all(BASE, simulate, fetcher=fetcher, clock=clock, sleep=clock.sleep)


class ChecksTest(unittest.TestCase):
    def test_healthy_site_passes_all_three_journeys(self):
        results = run(healthy_site)
        self.assertEqual([r.ok for r in results], [True, True, True])
        self.assertEqual(
            [r.url for r in results],
            [
                f"{BASE}/api/health",
                f"{BASE}/track/BT-DEM22",
                f"{BASE}/api/public/track/BT-DEM22",
            ],
        )

    def test_simulated_failure_adds_one_failing_check_without_retrying(self):
        clock = FakeClock()
        results = run(healthy_site, simulate=True, clock=clock)
        self.assertEqual([r.ok for r in results], [True, True, True, False])
        simulated = results[-1]
        self.assertEqual(simulated.url, f"{BASE}{uc.SIMULATED_PATH}")
        self.assertEqual((simulated.status, simulated.attempts), (404, 1))
        self.assertEqual(simulated.detail, "expected HTTP 200, got 404")
        self.assertEqual(clock.sleeps, [])

    def test_degraded_database_fails_health(self):
        def site(url):
            if url.endswith("/api/health"):
                return json_response(503, {"status": "degraded", "database": "error"})
            return healthy_site(url)

        health = run(site)[0]
        self.assertFalse(health.ok)
        self.assertEqual(health.status, 503)

    def test_health_200_but_database_error_fails(self):
        def site(url):
            if url.endswith("/api/health"):
                return json_response(200, {"status": "ok", "database": "error"})
            return healthy_site(url)

        self.assertIn("database='error'", run(site)[0].detail)

    def test_tracking_page_must_be_html(self):
        def site(url):
            if url.endswith("/track/BT-DEM22") and "/api/" not in url:
                return json_response(404, {"error": {}})
            return healthy_site(url)

        page = run(site)[1]
        self.assertFalse(page.ok)

    def test_extra_public_field_fails_and_reports_names_not_values(self):
        def site(url):
            if "/api/public/track/" in url:
                return json_response(200, {**TRACKING, "customer_phone": "+50600000101"})
            return healthy_site(url)

        lookup = run(site)[2]
        self.assertFalse(lookup.ok)
        self.assertIn("customer_phone", lookup.detail)
        self.assertNotIn("+50600000101", lookup.detail)

    def test_cold_start_is_retried_until_it_answers(self):
        calls = []

        def waking(url):
            calls.append(url)
            if len(calls) <= 3:
                raise TimeoutError("timed out")
            return healthy_site(url)

        clock = FakeClock()
        health = run(waking, clock=clock)[0]
        self.assertTrue(health.ok)
        self.assertEqual(health.attempts, 4)
        self.assertEqual(clock.sleeps, [10, 10, 10])

    def test_5xx_is_retried_but_gives_up_after_the_budget(self):
        clock = FakeClock()
        result = uc.run_check(
            uc.checks(False)[0],
            BASE,
            fetcher=lambda url: json_response(502, {}),
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 502)
        self.assertLessEqual(clock.now, uc.RETRY_BUDGET)
        self.assertEqual(result.attempts, len(clock.sleeps) + 1)
        self.assertGreater(result.attempts, 1)

    def test_connection_refused_is_reported_without_a_status(self):
        clock = FakeClock()

        def refused(url):
            raise ConnectionRefusedError

        result = uc.run_check(
            uc.checks(False)[0], BASE, fetcher=refused, clock=clock, sleep=clock.sleep
        )
        self.assertFalse(result.ok)
        self.assertIsNone(result.status)
        self.assertEqual(result.detail, "request failed: ConnectionRefusedError")

    def test_4xx_is_not_retried(self):
        clock = FakeClock()
        result = uc.run_check(
            uc.checks(False)[2],
            BASE,
            fetcher=lambda url: json_response(404, {}),
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertEqual((result.ok, result.attempts, clock.sleeps), (False, 1, []))


class SummaryTest(unittest.TestCase):
    def test_summary_lists_each_check_and_the_run(self):
        results = run(healthy_site, simulate=True)
        text = uc.summary_markdown(
            results,
            "https://github.com/o/r/actions/runs/1",
            datetime(2026, 10, 21, 22, 15, tzinfo=UTC),
        )
        self.assertIn(uc.MARKER, text)
        self.assertIn("**1 of 4 checks failed** at 2026-10-21 22:15 UTC.", text)
        self.assertIn("❌ FAIL | 404", text)
        self.assertIn("Run: https://github.com/o/r/actions/runs/1", text)
        self.assertNotIn("Lenovo", text)  # no response content in the report

    def test_docs_link_is_absolute_for_issues_and_job_summaries(self):
        import os
        from unittest import mock

        env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r"}
        with mock.patch.dict(os.environ, env):
            text = uc.summary_markdown([], None, datetime(2026, 1, 1, tzinfo=UTC))
        self.assertIn("(https://github.com/o/r/blob/main/ops/alerting.md#how-to-respond)", text)

    def test_slow_responses_are_marked(self):
        result = uc.Result("Health", f"{BASE}/api/health", True, 200, 7000, "", 1)
        text = uc.summary_markdown([result], None, datetime(2026, 1, 1, tzinfo=UTC))
        self.assertIn("7000 ms (slow)", text)


class FakeGh:
    def __init__(self, open_issues=()):
        self.issues = list(open_issues)
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        if args[:2] == ["issue", "create"]:
            return "https://github.com/o/r/issues/42\n"
        return ""


class ReportIssueTest(unittest.TestCase):
    def failing(self):
        return run(healthy_site, simulate=True)

    def test_failure_opens_one_alert_issue(self):
        gh = FakeGh()
        action = uc.report_issue(self.failing(), "SUMMARY", gh)
        self.assertEqual(action, "opened https://github.com/o/r/issues/42")
        create = gh.calls[-1]
        self.assertEqual(create[:4], ["issue", "create", "--label", "alert"])
        title = create[create.index("--title") + 1]
        self.assertEqual(title, "Uptime alert: Simulated failure (test only) failing")
        self.assertEqual(create[create.index("--body") + 1], "SUMMARY")

    def test_failure_with_an_open_alert_comments_instead_of_duplicating(self):
        gh = FakeGh([{"number": 15, "title": "Uptime alert: Health failing"}])
        action = uc.report_issue(self.failing(), "SUMMARY", gh)
        self.assertEqual(action, "commented on #15 (still failing)")
        self.assertFalse(any(c[:2] == ["issue", "create"] for c in gh.calls))
        self.assertEqual(gh.calls[-1][:3], ["issue", "comment", "15"])

    def test_recovery_comments_and_closes(self):
        gh = FakeGh([{"number": 15, "title": "Uptime alert: Health failing"}])
        action = uc.report_issue(run(healthy_site), "SUMMARY", gh)
        self.assertEqual(action, "closed #15 (recovered)")
        self.assertEqual(gh.calls[-2][:3], ["issue", "comment", "15"])
        self.assertTrue(gh.calls[-2][-1].startswith("Recovered."))
        self.assertEqual(gh.calls[-1], ["issue", "close", "15", "--reason", "completed"])

    def test_success_without_open_alert_does_nothing(self):
        gh = FakeGh()
        self.assertEqual(
            uc.report_issue(run(healthy_site), "S", gh), "no alert open, nothing to do"
        )
        self.assertEqual([c[:2] for c in gh.calls], [["issue", "list"]])

    def test_other_alert_labelled_issues_are_never_touched(self):
        # e.g. issue #7 itself carries the `alert` label but is not an uptime alert.
        gh = FakeGh([{"number": 7, "title": "Synthetic uptime alert on user impact"}])
        self.assertEqual(
            uc.report_issue(run(healthy_site), "S", gh), "no alert open, nothing to do"
        )
        uc.report_issue(self.failing(), "S", gh)
        self.assertEqual(gh.calls[-1][:2], ["issue", "create"])


class MainTest(unittest.TestCase):
    def test_missing_base_url_is_an_error(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(uc.main([]), 2)


if __name__ == "__main__":
    unittest.main()
