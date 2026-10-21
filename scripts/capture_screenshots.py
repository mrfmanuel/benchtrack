#!/usr/bin/env python3
"""Capture the README screenshots from a running BenchTrack with seed data only.

    docker compose up -d --build --wait                 # local app (seeded on first start)
    $env:BENCHTRACK_URL = "http://127.0.0.1:8000"       # or: export BENCHTRACK_URL=...
    $env:BENCHTRACK_TOKEN = "<local staff token>"       # typed by you, never printed
    uv run --no-project --with playwright python scripts/capture_screenshots.py

Writes PNGs to docs/screenshots/. The staff token is put into localStorage by an init
script before the app loads; it is never typed into a visible field, never printed, and
every page is checked not to contain it before its screenshot is taken. Point this only at
an environment with fictional data (the seed), never at production.

Playwright uses its own Chromium if installed (`playwright install chromium`), else the
system Chrome (set BROWSER_CHANNEL=msedge to use Edge).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Error, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
STORAGE_KEY = "benchtrack.staffToken"  # frontend/src/lib/tokenStore.ts
DETAIL_CODE = "BT-DEM28"  # seed ticket: received → diagnosing → repairing → ready
DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 390, "height": 844}


def launch(playwright) -> Browser:
    channel = os.environ.get("BROWSER_CHANNEL")
    if channel:
        return playwright.chromium.launch(channel=channel)
    try:
        return playwright.chromium.launch()
    except Error:
        return playwright.chromium.launch(channel="chrome")


def staff_context(browser: Browser, token: str, **options) -> BrowserContext:
    context = browser.new_context(**options)
    context.add_init_script(f"localStorage.setItem({STORAGE_KEY!r}, {json.dumps(token)});")
    return context


def shoot(page: Page, url: str, name: str, token: str, wait_for: str, full_page=True) -> None:
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.get_by_text(wait_for, exact=False).first.wait_for()
    if token in page.content():
        raise SystemExit(f"Refusing to save {name}: the page contains the staff token.")
    path = OUT / name
    page.screenshot(path=path, full_page=full_page)
    print(f"saved {path.relative_to(ROOT).as_posix()}")


def ticket_id(context: BrowserContext, base: str, token: str, code: str) -> int:
    response = context.request.get(
        f"{base}/api/tickets", params={"q": code}, headers={"Authorization": f"Bearer {token}"}
    )
    if response.status != 200:
        raise SystemExit(f"Ticket lookup failed with HTTP {response.status} (check the token).")
    items = [t for t in response.json()["items"] if t["tracking_code"] == code]
    if not items:
        raise SystemExit(f"Seed ticket {code} not found: run the seed first.")
    return items[0]["id"]


def main() -> int:
    base = os.environ.get("BENCHTRACK_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.environ.get("BENCHTRACK_TOKEN", "")
    if not token:
        print("Set BENCHTRACK_TOKEN (the local staff token).", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = launch(playwright)

        desktop = staff_context(browser, token, viewport=DESKTOP)
        page = desktop.new_page()
        tid = ticket_id(desktop, base, token, DETAIL_CODE)
        shoot(page, f"{base}/dashboard", "dashboard.png", token, "Stale")
        shoot(page, f"{base}/tickets", "tickets.png", token, DETAIL_CODE)
        shoot(page, f"{base}/tickets/{tid}", "ticket-detail.png", token, "Timeline")
        page.emulate_media(media="print")
        shoot(page, f"{base}/tickets/{tid}/receipt", "receipt.png", token, DETAIL_CODE)
        desktop.close()

        public = browser.new_context(viewport=DESKTOP)  # no token at all
        shoot(public.new_page(), f"{base}/track/{DETAIL_CODE}", "tracking.png", token, "Ready")
        public.close()

        mobile = staff_context(
            browser, token, viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True
        )
        shoot(mobile.new_page(), f"{base}/dashboard", "dashboard-mobile.png", token, "Stale")
        mobile.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
