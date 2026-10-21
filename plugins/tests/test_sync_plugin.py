"""Tests for plugins/sync_plugin.py (stdlib unittest, like agent-hooks/tests)."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "sync_plugin.py"
spec = importlib.util.spec_from_file_location("sync_plugin", SCRIPT)
sync_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_plugin)

SOURCES = {
    "agent-capabilities/skills/demo-skill/SKILL.md": "---\nname: demo-skill\n---\n",
    "agent-capabilities/agents/demo-agent.md": "---\nname: demo-agent\n---\n",
    "agent-hooks/guard.py": "# guard\n",
    "agent-hooks/ruff_check.py": "# ruff\n",
    "mcp-server/pyproject.toml": "[project]\n",
    "mcp-server/uv.lock": "version = 1\n",
    "mcp-server/.python-version": "3.12\n",
    "mcp-server/README.md": "# MCP\n",
    "mcp-server/src/demo_mcp/__init__.py": "",
}


class RealRepoTest(unittest.TestCase):
    def test_repo_copies_are_in_sync(self):
        self.assertEqual(sync_plugin.check(sync_plugin.expected_files()), [])

    def test_subagent_and_skills_are_available_without_the_plugin(self):
        root = sync_plugin.ROOT
        plugin = root / "plugins" / "benchtrack-dev"
        expected = sync_plugin.expected_files()
        self.assertIn(root / ".claude" / "agents" / "contract-reviewer.md", expected)
        for skill in ("contract-first-endpoint", "release-check"):
            self.assertIn(root / ".claude" / "skills" / skill / "SKILL.md", expected)
            self.assertIn(plugin / "skills" / skill / "SKILL.md", expected)

    def test_hand_written_files_are_not_managed(self):
        root = sync_plugin.ROOT
        managed = sync_plugin.managed_dirs()
        for path in (
            root / ".claude" / "settings.json",
            root / "plugins" / "benchtrack-dev" / ".claude-plugin" / "plugin.json",
            root / "plugins" / "benchtrack-dev" / "hooks" / "hooks.json",
        ):
            self.assertFalse(any(path.is_relative_to(d) for d in managed), path)


class TempRepoTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel, text in SOURCES.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        for name, value in {
            "ROOT": self.root,
            "PLUGIN": self.root / "plugins" / "benchtrack-dev",
            "REPO_CLAUDE": self.root / ".claude",
        }.items():
            patcher = mock.patch.object(sync_plugin, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def sync(self):
        with redirect_stdout(io.StringIO()):
            sync_plugin.sync(sync_plugin.expected_files())

    def problems(self):
        return sync_plugin.check(sync_plugin.expected_files())

    def test_missing_copies_are_reported_then_synced(self):
        problems = self.problems()
        self.assertIn(
            "missing: .claude/agents/demo-agent.md (from agent-capabilities/agents/demo-agent.md)",
            problems,
        )
        self.assertIn(
            "missing: .claude/skills/demo-skill/SKILL.md "
            "(from agent-capabilities/skills/demo-skill/SKILL.md)",
            problems,
        )
        self.sync()
        self.assertEqual(self.problems(), [])
        self.assertTrue((self.root / ".claude" / "agents" / "demo-agent.md").is_file())
        self.assertTrue((self.root / "plugins/benchtrack-dev/agents/demo-agent.md").is_file())
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(), "{}")

    def test_edited_copy_in_dot_claude_is_drift(self):
        self.sync()
        (self.root / ".claude" / "agents" / "demo-agent.md").write_text("edited\n")
        self.assertEqual(
            self.problems(),
            [
                (
                    "differs: .claude/agents/demo-agent.md "
                    "(from agent-capabilities/agents/demo-agent.md)"
                )
            ],
        )

    def test_unsourced_file_in_dot_claude_skills_is_drift(self):
        self.sync()
        extra = self.root / ".claude" / "skills" / "stray" / "SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("x\n")
        self.assertEqual(self.problems(), ["extra: .claude/skills/stray/SKILL.md (no source)"])
        self.sync()
        self.assertFalse(extra.exists())

    def test_tool_caches_inside_a_copy_are_ignored(self):
        self.sync()
        for cache in (".ruff_cache", ".pytest_cache", "__pycache__"):
            path = self.root / "plugins/benchtrack-dev/mcp-server" / cache / "data"
            path.parent.mkdir(parents=True)
            path.write_text("cache\n")
        self.assertEqual(self.problems(), [])

    def test_line_endings_do_not_count_as_drift(self):
        self.sync()
        copy = self.root / ".claude" / "agents" / "demo-agent.md"
        copy.write_bytes(copy.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.problems(), [])

    def test_check_exit_code(self):
        with redirect_stdout(io.StringIO()) as out, mock.patch("sys.argv", ["x", "--check"]):
            self.assertEqual(sync_plugin.main(), 1)
        self.assertIn("out of date", out.getvalue())
        self.sync()
        with redirect_stdout(io.StringIO()), mock.patch("sys.argv", ["x", "--check"]):
            self.assertEqual(sync_plugin.main(), 0)


if __name__ == "__main__":
    unittest.main()
