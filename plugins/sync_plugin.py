#!/usr/bin/env python3
"""Copy the agent extension pack sources into the self-contained plugin.

Claude Code plugins must not reference files outside their own directory, so
plugins/benchtrack-dev/ carries copies of the skills, the subagent, the hook scripts and the
MCP server. The sources stay the single place to edit:

    agent-capabilities/skills/<name>/  -> plugins/benchtrack-dev/skills/<name>/
    agent-capabilities/agents/*.md     -> plugins/benchtrack-dev/agents/
    agent-hooks/{guard,ruff_check}.py  -> plugins/benchtrack-dev/hooks/
    mcp-server/ (source, lockfile)     -> plugins/benchtrack-dev/mcp-server/

The plugin's own files (.claude-plugin/plugin.json, hooks/hooks.json, .mcp.json, README.md)
are written by hand and not touched.

    python plugins/sync_plugin.py           # update the copies
    python plugins/sync_plugin.py --check   # CI: exit 1 if a copy differs from its source
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "benchtrack-dev"

MCP_FILES = ("pyproject.toml", "uv.lock", ".python-version", "README.md")
HOOK_SCRIPTS = ("guard.py", "ruff_check.py")


def is_source_file(path: Path) -> bool:
    return path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"


def expected_files() -> dict[Path, Path]:
    """Plugin path -> source path for every synced file."""
    mapping: dict[Path, Path] = {}
    for skill in sorted((ROOT / "agent-capabilities" / "skills").iterdir()):
        for src in sorted(skill.rglob("*")):
            if is_source_file(src):
                mapping[PLUGIN / "skills" / skill.name / src.relative_to(skill)] = src
    for src in sorted((ROOT / "agent-capabilities" / "agents").glob("*.md")):
        mapping[PLUGIN / "agents" / src.name] = src
    for name in HOOK_SCRIPTS:
        mapping[PLUGIN / "hooks" / name] = ROOT / "agent-hooks" / name
    mcp = ROOT / "mcp-server"
    for name in MCP_FILES:
        mapping[PLUGIN / "mcp-server" / name] = mcp / name
    for src in sorted((mcp / "src").rglob("*")):
        if is_source_file(src):
            mapping[PLUGIN / "mcp-server" / src.relative_to(mcp)] = src
    return mapping


def managed_dirs() -> list[Path]:
    return [PLUGIN / "skills", PLUGIN / "agents", PLUGIN / "mcp-server"]


def normalized(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def check(mapping: dict[Path, Path]) -> list[str]:
    problems = []
    for dest, src in mapping.items():
        rel = dest.relative_to(ROOT).as_posix()
        if not dest.is_file():
            problems.append(f"missing: {rel} (from {src.relative_to(ROOT).as_posix()})")
        elif normalized(dest) != normalized(src):
            problems.append(f"differs: {rel} (from {src.relative_to(ROOT).as_posix()})")
    for directory in managed_dirs():
        for path in directory.rglob("*"):
            if is_source_file(path) and path not in mapping:
                problems.append(f"extra: {path.relative_to(ROOT).as_posix()} (no source)")
    return problems


def sync(mapping: dict[Path, Path]) -> None:
    for directory in managed_dirs():
        if directory.exists():
            shutil.rmtree(directory)
    for dest, src in mapping.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(normalized(src))
    print(f"Synced {len(mapping)} files into {PLUGIN.relative_to(ROOT).as_posix()}/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the plugin copy drifted")
    args = parser.parse_args()
    mapping = expected_files()
    if args.check:
        problems = check(mapping)
        if problems:
            print("Plugin copy is out of date; run `python plugins/sync_plugin.py`:")
            print("\n".join(f"  {p}" for p in problems))
            return 1
        print(f"Plugin copy is in sync ({len(mapping)} files).")
        return 0
    sync(mapping)
    return 0


if __name__ == "__main__":
    sys.exit(main())
