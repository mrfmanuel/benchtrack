#!/usr/bin/env python3
"""Run every test suite with one command (Windows, Linux, macOS).

    uv run --no-project python scripts/test_all.py                    # everything
    uv run --no-project python scripts/test_all.py --skip-integration # no Docker needed

1. Starts the Compose PostgreSQL (`docker compose up -d db --wait`) for the integration tests.
2. Backend: unit + API + integration in one pytest run. Uses TEST_DATABASE_URL if set, else
   the Compose default `…@127.0.0.1:<DB_PORT>/benchtrack_test` (dropped and recreated by the
   tests); DB_PORT comes from the shell or .env like Compose reads it, default 5433.
3. Frontend: Vitest (runs `npm ci` first if node_modules is missing).
4. Agent pack: guard/ruff hook tests, sync-script tests, plugin/.claude copies in sync, MCP server.

Exits non-zero if any suite fails, and prints a summary. CI runs the same suites as separate
jobs (.github/workflows/ci.yml).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DB = "postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:{port}/benchtrack_test"
PORT_VARS = ("DB_PORT", "POSTGRES_PORT")  # same precedence as docker-compose.yml


def db_port() -> str:
    """Host port of the Compose PostgreSQL: shell environment first, then .env (like Compose).

    Only the two port variables are read from .env; nothing else in it is touched.
    """
    from_env_file: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in PORT_VARS:
                from_env_file[key.strip()] = value.strip().strip("\"'")
    for name in PORT_VARS:
        for source in (os.environ, from_env_file):
            if source.get(name):
                return source[name]
    return "5433"


def tool(name: str) -> str:
    """Full path of an executable (npm is npm.cmd on Windows)."""
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"`{name}` not found on PATH; see README.md for requirements.")
    return path


def run(label: str, args: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
    print(f"\n=== {label} ===\n$ {' '.join(args)}  (in {cwd.relative_to(ROOT).as_posix() or '.'})")
    sys.stdout.flush()
    started = time.monotonic()
    # Fixed argument lists built above, no shell: nothing untrusted reaches the command.
    ok = subprocess.run(args, cwd=cwd, env=env, check=False).returncode == 0  # noqa: S603
    RESULTS.append((label, ok, time.monotonic() - started))
    return ok


RESULTS: list[tuple[str, bool, float]] = []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-integration", action="store_true", help="skip PostgreSQL integration tests"
    )
    args = parser.parse_args()

    uv, py = tool("uv"), sys.executable
    backend_env = dict(os.environ)
    if args.skip_integration:
        marker = "not integration"
    else:
        marker = "integration or not integration"
        backend_env.setdefault("TEST_DATABASE_URL", DEFAULT_TEST_DB.format(port=db_port()))
        if not run(
            "PostgreSQL (Compose)",
            [tool("docker"), "compose", "up", "-d", "db", "--wait"],
            ROOT,
        ):
            print("Could not start PostgreSQL; use --skip-integration to run without it.")

    run(
        "Backend: unit + API" + ("" if args.skip_integration else " + integration"),
        [uv, "run", "pytest", "-q", "-m", marker],
        ROOT / "backend",
        backend_env,
    )

    npm = tool("npm")
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").is_dir():
        run("Frontend: npm ci", [npm, "ci"], frontend)
    run("Frontend: Vitest", [npm, "test"], frontend)

    run("Agent hooks", [py, "-m", "unittest", "discover", "-s", "agent-hooks/tests"], ROOT)
    run("Sync script", [py, "-m", "unittest", "discover", "-s", "plugins/tests"], ROOT)
    run("Scripts", [py, "-m", "unittest", "discover", "-s", "scripts/tests"], ROOT)
    run("Plugin and .claude/ copies", [py, "plugins/sync_plugin.py", "--check"], ROOT)
    mcp = ROOT / "mcp-server"
    # Once the venv exists, don't re-sync it: a Claude Code session using the project's MCP
    # server keeps benchtrack-mcp.exe open on Windows, and uv can't replace it.
    sync = ["--no-sync"] if (mcp / ".venv").is_dir() else ["--frozen"]
    run("MCP server", [uv, "run", *sync, "pytest", "-q"], mcp)

    print("\n=== Summary ===")
    for label, ok, seconds in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {label}  ({seconds:.0f} s)")
    failed = [label for label, ok, _ in RESULTS if not ok]
    print("All suites passed." if not failed else f"{len(failed)} suite(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
