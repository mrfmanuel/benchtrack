"""Unit tests for the PreToolUse guard (stdlib unittest; run in CI).

python -m unittest discover -s agent-hooks/tests -v
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guard  # noqa: E402


def bash(command: str, cwd: str | None = None) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}


def ps(command: str) -> dict:
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


def tool(name: str, **tool_input) -> dict:
    return {"tool_name": name, "tool_input": tool_input}


class GuardCase(unittest.TestCase):
    def setUp(self):
        # Default: not on main, so bare `git push` is allowed unless a test says otherwise.
        patcher = mock.patch.object(guard, "current_branch", return_value="feat/x")
        self.branch = patcher.start()
        self.addCleanup(patcher.stop)

    def assertBlocked(self, event, reason_part=""):
        block = guard.evaluate(event)
        self.assertIsNotNone(block, f"expected a block for {event['tool_input']}")
        self.assertIn(reason_part.lower(), block.reason.lower())

    def assertAllowed(self, event):
        block = guard.evaluate(event)
        self.assertIsNone(block, f"unexpected block for {event['tool_input']}: {block}")


class EnvFiles(GuardCase):
    def test_file_tools_on_env_files_are_blocked(self):
        for name, key in [
            ("Read", "file_path"),
            ("Edit", "file_path"),
            ("Write", "file_path"),
            ("MultiEdit", "file_path"),
            ("NotebookEdit", "notebook_path"),
            ("Grep", "path"),
        ]:
            for path in [
                ".env",
                "/repo/.env",
                "E:\\repo\\backend\\.env",
                "./.env.local",
                ".env.production",
                ".envrc",
            ]:
                with self.subTest(tool=name, path=path):
                    self.assertBlocked(tool(name, **{key: path}), "secrets file")

    def test_env_example_and_lookalikes_are_allowed(self):
        for path in [
            ".env.example",
            "/repo/.env.example",
            "frontend/.env.example",
            "docs/environment.md",
            "backend/app/config.py",
            "src/vite-env.d.ts",
        ]:
            with self.subTest(path=path):
                self.assertAllowed(tool("Read", file_path=path))
                self.assertAllowed(tool("Edit", file_path=path))

    def test_grep_glob_on_env_files_is_blocked(self):
        self.assertBlocked(tool("Grep", pattern="TOKEN", glob=".env*"), ".env")
        self.assertAllowed(tool("Grep", pattern="TOKEN", glob="*.py"))
        self.assertAllowed(tool("Glob", pattern="**/.env*"))  # lists names only

    def test_shell_reads_of_env_files_are_blocked(self):
        for command in [
            "cat .env",
            "cat ./.env",
            "head -n 3 backend/.env",
            "less .env.local",
            "grep STAFF_TOKEN .env",
            "type .env",
            "Get-Content .env",
            "source .env",
            ". .env",
            "cat < .env",
            "cp .env /tmp/x",
            "cp .env.example .env",
            "awk -F= '/TOKEN/{print $2}' .env",
            "git show HEAD:.env",
            "base64 .env",
            "docker compose --env-file=.env.prod up",
            "echo ok && cat .env",
            "sh -c 'cat .env'",
            'bash -c "tail .env"',
            "x=$(cat .env)",
            "y=`cat .env`",
            "python -c \"print(open('.env').read())\"",
            "uv run python -c \"open('.env')\"",
            "node -e \"require('fs').readFileSync('.env')\"",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command), "secrets file")

    def test_escaped_backticks_are_text_not_substitutions(self):
        # Found live: a prompt passed to `claude -p "... \`git push --force\` ..."` was blocked.
        self.assertAllowed(bash(r'claude -p "Explain why \`git push --force\` is risky"'))
        self.assertBlocked(bash("echo `git push --force origin x`"), "force")
        self.assertBlocked(bash('x="$(cat .env)"'), "secrets file")

    def test_env_file_in_heredoc_for_an_interpreter_is_blocked(self):
        self.assertBlocked(bash("python - <<'EOF'\nprint(open('.env').read())\nEOF"), ".env")

    def test_mentions_of_env_files_that_do_not_read_them_are_allowed(self):
        for command in [
            'git commit -m "Ignore .env files and never rm -rf anything"',
            "git commit -q -F - <<'EOF'\nDocument .env handling; rm -rf and DROP TABLE are banned\nEOF",
            "git check-ignore -v .env",
            "git ls-files .env.example",
            "git status --short",
            "git add .env.example docs/deployment.md",
            "cat .env.example",
            "cp .env.example /tmp/review.txt",
            'gh pr create --title "Add .env docs"',
            "cat > docs/x.md <<'EOF'\nNever read .env or print STAFF_TOKEN\nEOF",
            'node -e "console.log(process.env.NODE_ENV)"',
            "grep -n import.meta.env src/config.ts",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))


class Destructive(GuardCase):
    def test_rm_rf_in_every_spelling_is_blocked(self):
        for command in [
            "rm -rf build",
            "rm -fr build",
            "rm -Rf x",
            "rm -r -f x",
            "rm --recursive --force x",
            "sudo rm -rf /",
            "/bin/rm -rf node_modules",
            "find . -name '*.pyc' -exec rm -rf {} +",
            "echo hi; rm -rf dist",
            "bash -c 'rm -rf /tmp/x'",
            "timeout 5 rm -rf x",
            "FOO=1 rm -rf x",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command), "rm -rf")

    def test_plain_rm_is_allowed(self):
        for command in [
            "rm -f backend/tests/_tmp.py",
            "rm -r empty_dir",
            "rm file.txt",
            "git rm --cached x",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))

    def test_powershell_recursive_force_delete_is_blocked(self):
        self.assertBlocked(ps("Remove-Item -Recurse -Force .\\dist"), "Remove-Item")
        self.assertBlocked(ps("rm -Recurse -Force x"), "Remove-Item")
        self.assertAllowed(ps("Remove-Item .\\tmp.txt"))

    def test_git_reset_hard_is_blocked(self):
        self.assertBlocked(bash("git reset --hard origin/main"), "reset --hard")
        self.assertBlocked(bash("git -C backend reset --hard"), "reset --hard")
        self.assertAllowed(bash("git reset HEAD~1"))
        self.assertAllowed(bash("git reset --soft HEAD~1"))

    def test_destructive_sql_is_blocked(self):
        for command in [
            'psql -U benchtrack -c "DROP TABLE tickets"',
            "docker compose exec db psql -U benchtrack -d benchtrack -c 'truncate tickets'",
            'sqlite3 benchtrack.db "drop table customers;"',
            "psql <<'EOF'\nDROP SCHEMA public CASCADE;\nEOF",
            "uv run python -c \"conn.execute('DROP DATABASE benchtrack')\"",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command), "destructive sql")

    def test_safe_sql_and_mentions_are_allowed(self):
        self.assertAllowed(
            bash('psql -U benchtrack -c "select tracking_code, status from tickets limit 5;"')
        )
        self.assertAllowed(bash('git commit -m "Never DROP TABLE in migrations"'))
        self.assertAllowed(bash("grep -rn TRUNCATE backend/"))

    def test_docker_destruction_is_blocked(self):
        for command in [
            "docker system prune -af",
            "docker volume rm finalproject_pgdata",
            "docker volume prune -f",
            "podman system prune",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command))

    def test_ordinary_docker_is_allowed(self):
        for command in [
            "docker compose up --build -d --wait",
            "docker compose ps",
            "docker compose logs app --since 10m",
            "docker volume ls",
            "docker compose down",
            "docker compose config --quiet",
            "docker inspect finalproject-app-1 --format '{{.State.Health.Status}}'",
            "docker compose exec -T app python -m app.seed",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))


class GitPush(GuardCase):
    def test_force_pushes_are_blocked(self):
        for command in [
            "git push --force",
            "git push -f origin feat/x",
            "git push origin -f",
            "git push --force-with-lease origin feat/x",
            "git push -uf origin x",
            "git push origin +feat/x",
            "git push --mirror",
            "git push --all origin",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command))

    def test_pushes_to_main_are_blocked(self):
        for command in [
            "git push origin main",
            "git push -q origin main",
            "git push origin HEAD:main",
            "git push origin feat/x:main",
            "git push origin refs/heads/main",
            "git -C . push origin main",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command), "main")

    def test_bare_push_on_main_is_blocked(self):
        self.branch.return_value = "main"
        self.assertBlocked(bash("git push"), "main")
        self.assertBlocked(bash("git push origin"), "main")
        self.assertBlocked(bash("git push origin HEAD"), "main")

    def test_feature_branch_pushes_are_allowed(self):
        for command in [
            "git push",
            "git push -u origin feat/agent-extension-pack",
            "git push -q -u origin security/http-hardening",
            "git push origin HEAD",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))

    def test_branch_lookup_uses_the_session_cwd(self):
        guard.evaluate(bash("git push", cwd="/some/repo"))
        self.branch.assert_called_with("/some/repo")


class Secrets(GuardCase):
    def test_commands_printing_secrets_are_blocked(self):
        for command in [
            "printenv",
            "printenv STAFF_TOKEN",
            "env",
            "env -0",
            "set",
            "export -p",
            "echo $STAFF_TOKEN",
            'echo "token=${STAFF_TOKEN}"',
            "printf '%s' \"$DATABASE_URL\"",
            "echo $RENDER_DEPLOY_HOOK_URL",
            "echo $GITHUB_TOKEN",
            "docker compose exec -T app printenv STAFF_TOKEN",
            "docker compose exec app env",
            "docker exec -it app sh -c 'echo $STAFF_TOKEN'",
            "docker compose config",
            "docker inspect finalproject-app-1",
            "docker inspect finalproject-app-1 --format '{{json .Config.Env}}'",
            "python -c \"import os; print(os.environ['STAFF_TOKEN'])\"",
            "uv run python -c \"import os; print(os.getenv('BENCHTRACK_TOKEN'))\"",
            'node -e "console.log(process.env.STAFF_TOKEN)"',
        ]:
            with self.subTest(command=command):
                self.assertBlocked(bash(command))

    def test_powershell_secret_printing_is_blocked(self):
        for command in [
            "Get-ChildItem env:",
            "gci env:STAFF_TOKEN",
            "dir env:",
            "Write-Output $env:STAFF_TOKEN",
            "echo $env:DATABASE_URL",
            "$env:STAFF_TOKEN",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(ps(command))

    def test_using_or_checking_secrets_without_printing_is_allowed(self):
        for command in [
            '[ -n "$STAFF_TOKEN" ] && echo set',
            "echo $HOME",
            "echo $APP_PORT",
            "set -euo pipefail",
            "export APP_PORT=8010",
            "env APP_PORT=8010 docker compose up -d",
            'curl -s -H "Authorization: Bearer $BENCHTRACK_TOKEN" http://127.0.0.1:8000/api/dashboard',
            "gh secret list",
            "python -c \"import os; print(os.environ.get('HOME'))\"",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))
        self.assertAllowed(ps('$env:APP_PORT = "8010"; docker compose up -d --wait'))


class EveryDayCommands(GuardCase):
    """Commands actually used while building BenchTrack must keep working."""

    def test_allowed(self):
        for command in [
            "uv run pytest -q",
            "uv run ruff check . && uv run ruff format --check .",
            "npm test",
            "npm run lint",
            "npm run build",
            "git log --oneline -5",
            "git diff main...HEAD --stat",
            "gh run list --limit 4",
            "curl.exe -s http://127.0.0.1:8010/api/health",
            "npx --yes @redocly/cli@2.66.0 lint openapi.yaml",
            'MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/src" -w /src semgrep/semgrep:1.182.0 semgrep scan --config auto --error',
            "git commit -q -F - <<'EOF'\nAdd things\n\nCo-Authored-By: Claude\nEOF",
            "TEST_DATABASE_URL=postgresql+psycopg://u:p@127.0.0.1:5433/x_test uv run pytest -m integration",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(bash(command))

    def test_other_tools_are_not_inspected(self):
        self.assertAllowed(tool("WebFetch", url="https://example.com/.env"))
        self.assertAllowed({"tool_name": "Bash", "tool_input": "not-a-dict"})


class Parsing(unittest.TestCase):
    def test_segments_respect_quotes_substitutions_and_redirections(self):
        cases = {
            "a; b && c || d | e & f": ["a", "b", "c", "d", "e", "f"],
            'python -c "import os; print(1)"': ['python -c "import os; print(1)"'],
            "cmd 2>&1 | tee log": ["cmd 2>&1", "tee log"],
            "echo 'a;b' ; ls": ["echo 'a;b'", "ls"],
            "x=$(cd a; ls) && y": ["x=$(cd a; ls)", "y"],
            "cmd &> log": ["cmd &> log"],
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(guard.split_segments(command), expected)


class EntryPoint(unittest.TestCase):
    def run_main(self, stdin: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(stdin)),
            redirect_stdout(out),
            mock.patch.object(sys, "stderr", io.StringIO()),
        ):
            code = guard.main()
        return code, out.getvalue()

    def test_deny_is_reported_as_claude_code_json(self):
        code, out = self.run_main(json.dumps(bash("cat .env")))
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertTrue(decision["permissionDecisionReason"].startswith("BenchTrack guard: "))

    def test_allowed_calls_print_nothing(self):
        self.assertEqual(self.run_main(json.dumps(bash("npm test"))), (0, ""))

    def test_unreadable_input_fails_closed(self):
        code, out = self.run_main("{not json")
        self.assertEqual((code, out), (2, ""))


if __name__ == "__main__":
    unittest.main()
