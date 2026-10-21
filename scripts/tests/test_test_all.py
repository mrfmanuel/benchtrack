"""Tests for scripts/test_all.py helpers (stdlib unittest)."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "test_all.py"
spec = importlib.util.spec_from_file_location("test_all", SCRIPT)
test_all = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_all)


class DbPortTest(unittest.TestCase):
    """Same precedence as docker-compose.yml: ${DB_PORT:-${POSTGRES_PORT:-5433}}."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.object(test_all, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def port(self, env=None, env_file=None):
        if env_file is not None:
            (self.root / ".env").write_text(env_file, encoding="utf-8")
        with mock.patch.dict("os.environ", env or {}, clear=True):
            return test_all.db_port()

    def test_default_is_5433(self):
        self.assertEqual(self.port(), "5433")

    def test_db_port_from_env_file(self):
        self.assertEqual(self.port(env_file="STAFF_TOKEN=x\nDB_PORT=5434\n"), "5434")

    def test_shell_beats_env_file(self):
        self.assertEqual(self.port(env={"DB_PORT": "5435"}, env_file="DB_PORT=5434\n"), "5435")

    def test_legacy_postgres_port_is_a_fallback(self):
        self.assertEqual(self.port(env_file="POSTGRES_PORT=5436\n"), "5436")
        self.assertEqual(self.port(env_file="POSTGRES_PORT=5436\nDB_PORT=5434\n"), "5434")
        # DB_PORT in .env wins over POSTGRES_PORT in the shell, as in Compose.
        self.assertEqual(self.port(env={"POSTGRES_PORT": "5437"}, env_file="DB_PORT=5434"), "5434")

    def test_quotes_comments_and_empty_values(self):
        self.assertEqual(self.port(env_file='# DB_PORT=1\nDB_PORT="5438"\n'), "5438")
        self.assertEqual(self.port(env_file="DB_PORT=\n"), "5433")

    def test_default_url_uses_the_port(self):
        url = test_all.DEFAULT_TEST_DB.format(port="5434")
        self.assertIn("@127.0.0.1:5434/benchtrack_test", url)


if __name__ == "__main__":
    unittest.main()
