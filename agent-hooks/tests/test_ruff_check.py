"""Unit tests for the PostToolUse ruff hook (stdlib unittest; run in CI)."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ruff_check  # noqa: E402


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class RuffHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "backend").mkdir()
        (self.root / "backend" / "pyproject.toml").write_text("[project]\nname='x'\n")
        self.py = self.root / "backend" / "mod.py"
        self.py.write_text("x = 1\n")
        env = mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def event(self, path, tool="Edit") -> dict:
        return {"tool_name": tool, "cwd": str(self.root), "tool_input": {"file_path": str(path)}}

    def run_hook(self, event, completed=None):
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))),
            mock.patch.object(sys, "stderr", stderr),
            mock.patch.object(ruff_check.shutil, "which", return_value="uv"),
            mock.patch.object(
                ruff_check.subprocess, "run", return_value=completed or FakeCompleted(0)
            ) as run,
        ):
            code = ruff_check.main()
        return code, stderr.getvalue(), run

    def test_only_edited_python_files_inside_the_project_are_linted(self):
        outside = Path(tempfile.gettempdir()) / "outside_hook_test.py"
        outside.write_text("x = 1\n")
        self.addCleanup(outside.unlink)
        (self.root / "notes.md").write_text("# x\n")
        for event in [
            self.event(self.root / "notes.md"),
            self.event(outside),
            self.event(self.root / "missing.py"),
            self.event(self.py, tool="Read"),
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        ]:
            with self.subTest(event=event):
                code, _, run = self.run_hook(event)
                self.assertEqual(code, 0)
                run.assert_not_called()

    def test_clean_file_is_silent(self):
        code, err, run = self.run_hook(self.event(self.py))
        self.assertEqual((code, err), (0, ""))
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], ["uv", "run"])
        self.assertIn("ruff", argv)
        self.assertEqual(argv[-1], str(self.py))

    def test_findings_are_reported_back_to_the_agent(self):
        findings = "backend/mod.py:1:8: F401 `os` imported but unused\nFound 1 error."
        code, err, _ = self.run_hook(self.event(self.py), FakeCompleted(1, stdout=findings))
        self.assertEqual(code, 2)  # Claude Code shows stderr to the model
        self.assertIn("ruff check found problems in backend/mod.py", err)
        self.assertIn("F401", err)

    def test_ruff_crash_does_not_block(self):
        code, err, _ = self.run_hook(self.event(self.py), FakeCompleted(2, stderr="boom"))
        self.assertEqual(code, 1)
        self.assertIn("ruff failed", err)

    def test_relative_paths_resolve_against_cwd(self):
        code, _, run = self.run_hook(self.event("backend/mod.py"))
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.args[0][-1], str(self.py))

    def test_malformed_event_is_ignored(self):
        with mock.patch.object(sys, "stdin", io.StringIO("{nope")):
            self.assertEqual(ruff_check.main(), 0)


if __name__ == "__main__":
    unittest.main()
