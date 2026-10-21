#!/usr/bin/env python3
"""Claude Code PostToolUse hook: run `ruff check` on a Python file the agent just edited.

Problems are reported back to the agent (stderr + exit 2, which Claude Code shows to the model
after the edit), so it fixes them in the next step. Clean files, non-Python files and files
outside the project print nothing. If ruff cannot run at all, the hook says so without
blocking (exit 1).

Ruff comes from the backend's locked dev environment (`uv run --project backend`), so the
version matches CI. Configuration is the nearest pyproject.toml/ruff.toml to the edited file
(backend/, mcp-server/, agent-hooks/).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 60
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def project_dir(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()).resolve()


def target_file(event: dict) -> Path | None:
    if event.get("tool_name") not in EDIT_TOOLS:
        return None
    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw.endswith((".py", ".pyi")):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(event.get("cwd") or os.getcwd()) / path
    path = path.resolve()
    root = project_dir(event)
    if not path.is_file() or not path.is_relative_to(root):
        return None
    return path


def ruff_command(root: Path, path: Path) -> list[str] | None:
    uv = shutil.which("uv")
    if uv and (root / "backend" / "pyproject.toml").is_file():
        return [
            uv,
            "run",
            "--quiet",
            "--frozen",
            "--project",
            str(root / "backend"),
            "ruff",
            "check",
            "--output-format",
            "concise",
            "--force-exclude",
            str(path),
        ]
    ruff = shutil.which("ruff")
    return (
        [ruff, "check", "--output-format", "concise", "--force-exclude", str(path)]
        if ruff
        else None
    )


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0  # nothing to lint; never block an edit on a malformed event
    path = target_file(event)
    if path is None:
        return 0
    root = project_dir(event)
    command = ruff_command(root, path)
    if command is None:
        print("ruff_check hook: neither uv nor ruff found; skipped linting.", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"ruff_check hook: ruff timed out after {TIMEOUT_SECONDS}s.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ruff_check hook: could not run ruff ({exc}).", file=sys.stderr)
        return 1
    if result.returncode == 0:
        return 0
    output = (result.stdout or result.stderr).strip()
    if result.returncode == 1 and output:  # lint findings
        rel = path.relative_to(root).as_posix()
        print(
            f"ruff check found problems in {rel}; fix them before continuing:\n{output}",
            file=sys.stderr,
        )
        return 2
    print(
        f"ruff_check hook: ruff failed (exit {result.returncode}): {output[:500]}", file=sys.stderr
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
