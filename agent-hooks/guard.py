#!/usr/bin/env python3
"""Claude Code PreToolUse guard for BenchTrack (stdlib only, any OS).

Reads the hook event JSON on stdin. If the tool call is forbidden, prints a `deny` decision
with a reason (JSON on stdout, exit 0). Otherwise prints nothing and exits 0, and the
permission rules in .claude/settings.json decide as usual.

Blocked:
  * reading or editing `.env*` files (except `.env.example`), with file tools or in a shell
  * `rm -rf` (any flag spelling, also inside `find -exec`) and `Remove-Item -Recurse -Force`
  * `git push --force` / `-f` / `--force-with-lease` / `+refspec`, and any push to `main`
  * `git reset --hard`
  * SQL `DROP TABLE|SCHEMA|DATABASE` and `TRUNCATE` sent through a database client or script
  * `docker system prune`, `docker volume rm|prune`
  * commands that print secrets: `printenv`, bare `env`/`set`/`export`, PowerShell `env:`
    listings, echo/printf of secret-named variables, scripts printing secret env vars,
    `docker compose config` without `--quiet`, `docker inspect` of the environment

Commands are parsed, not grepped: compound commands are split, wrappers (`sudo`, `timeout`,
`uv run`, `docker compose exec`, `bash -c`, `$(...)`) are unwrapped, and heredoc bodies are
treated as data unless a shell or interpreter executes them. So a commit message that merely
mentions `.env` or `rm -rf` is allowed.

This is a guardrail against mistakes and prompt injection, not a sandbox: a process can still
read files indirectly. Permission deny rules in .claude/settings.json add a second layer.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field

MAIN_BRANCH = "main"
ALLOWED_ENV_FILES = {".env.example"}
MAX_DEPTH = 5

SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd"}
INTERPRETERS = {"python", "python3", "py", "node", "deno", "bun", "ruby", "perl", "php"}
DB_CLIENTS = {"psql", "sqlite3", "mysql", "mariadb", "sqlcmd", "pgcli"}
WRAPPERS = {"sudo", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob", "exec"}
PRINTERS = {"echo", "printf", "print", "write-output", "write-host", "say"}
FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"}
SHELL_TOOLS = {"Bash", "PowerShell"}
# git subcommands that name files without printing their content
GIT_PATH_ONLY = {
    "check-ignore",
    "ls-files",
    "status",
    "log",
    "add",
    "rm",
    "mv",
    "restore",
    "commit",
    "tag",
}

SECRET_NAME = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|DATABASE_URL|DEPLOY_HOOK|HOOK_URL|"
    r"CREDENTIAL|ACCESS_KEY",
    re.IGNORECASE,
)
SQL_RE = re.compile(r"\b(DROP\s+(TABLE|SCHEMA|DATABASE)|TRUNCATE)\b", re.IGNORECASE)
ENV_IN_CODE = re.compile(r"""['"`]((?:[^'"`\s]*[\\/])?\.env[\w.-]*)['"`]""")
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][\w-]*)\1")
# `$(...)` and unescaped backticks (a `\`` is a literal backtick, not a substitution).
SUBST_RE = re.compile(r"\$\(([^()]*(?:\([^()]*\)[^()]*)*)\)|(?<!\\)`((?:[^`\\]|\\.)*)(?<!\\)`")
VAR_REF = re.compile(r"\$\{?(?:env:)?([A-Za-z_][A-Za-z0-9_]*)|%([A-Za-z_][A-Za-z0-9_]*)%")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)


@dataclass(frozen=True)
class Block:
    reason: str


@dataclass
class Context:
    cwd: str | None = None
    depth: int = 0
    seen: set[str] = field(default_factory=set)


# --- Paths -------------------------------------------------------------------------------


def basename(path: str) -> str:
    return re.split(r"[\\/]", path.strip().strip("'\""))[-1]


def is_env_file(path: str) -> bool:
    name = basename(path)
    return name.startswith(".env") and name not in ALLOWED_ENV_FILES


def env_block(name: str) -> Block:
    return Block(
        f"'{name}' is a secrets file: reading, printing, copying or editing .env* is blocked "
        "(only .env.example is allowed). Use .env.example for variable names and ask the human "
        "for values."
    )


def check_file_tool(tool: str, tool_input: dict) -> Block | None:
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value and is_env_file(value):
            return env_block(value)
    pattern = tool_input.get("glob")
    if tool == "Grep" and isinstance(pattern, str) and is_env_file(pattern.lstrip("*/")):
        return Block("Searching inside .env files is blocked: they hold secrets.")
    return None


# --- Shell parsing -------------------------------------------------------------------------


def split_heredocs(command: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove heredoc bodies; return the rest plus (introducing line, body) pairs."""
    lines = command.split("\n")
    kept: list[str] = []
    bodies: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        if match := HEREDOC_RE.search(line):
            terminator, body = match.group(2), []
            while i < len(lines) and lines[i].strip() != terminator:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append((line, "\n".join(body)))
    return "\n".join(kept), bodies


def split_segments(command: str) -> list[str]:
    """Split on `;`, `&&`, `||`, `|`, `&` and newlines, but not inside quotes, `$(...)` or
    redirections such as `2>&1`."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    i = 0
    while i < len(command):
        c = command[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c == "\\" and i + 1 < len(command):
            buf.extend((c, command[i + 1]))
            i += 2
            continue
        elif command.startswith("$(", i):
            depth += 1
            buf.append("$(")
            i += 2
            continue
        elif c == ")" and depth:
            depth -= 1
            buf.append(c)
        elif (
            depth == 0
            and c in ";|\n"
            or (
                depth == 0
                and c == "&"
                and (i == 0 or command[i - 1] not in "<>")
                and command[i + 1 : i + 2] != ">"
            )
        ):
            j = i + 1
            while j < len(command) and command[j] in "&|":
                j += 1
            parts.append("".join(buf))
            buf = []
            i = j
            continue
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def prog(token: str) -> str:
    name = basename(token).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        name = name.removesuffix(suffix)
    return name


def strip_wrappers(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens):
        name = prog(tokens[i])
        if ASSIGNMENT.fullmatch(tokens[i]) or name in WRAPPERS:
            i += 1
        elif name == "timeout":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2 if re.fullmatch(r"[\d.]+[smhd]?", nxt) else 1
        elif name == "env" and i + 1 < len(tokens) and ASSIGNMENT.fullmatch(tokens[i + 1]):
            i += 1  # `env A=1 cmd`
        else:
            break
    return tokens[i:]


def skip_options(tokens: list[str], with_value: set[str]) -> list[str]:
    i = 0
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in with_value else 1
    return tokens[i:]


def inner_command(name: str, args: list[str]) -> list[str] | None:
    """The command run by `uv run ...`, `npx ...`, `docker [compose] exec|run ...`."""
    if name in ("uv", "uvx", "pipx", "poetry", "pdm") and args[:1] == ["run"]:
        return skip_options(
            args[1:],
            {
                "--directory",
                "--project",
                "--with",
                "--from",
                "--python",
                "--group",
                "--extra",
                "--env-file",
                "-p",
                "-w",
            },
        )
    if name in ("uvx", "npx", "pnpx", "bunx"):
        return skip_options(args, {"--from", "--with", "--python", "-p"})[1:]
    if name in ("docker", "podman"):
        rest = args[1:] if args[:1] == ["compose"] else args
        rest = skip_options(rest, {"-f", "--file", "-p", "--project-name", "--env-file"})
        if rest[:1] in (["exec"], ["run"]):
            after = skip_options(
                rest[1:],
                {
                    "-e",
                    "--env",
                    "-u",
                    "--user",
                    "-w",
                    "--workdir",
                    "--index",
                    "--name",
                    "--entrypoint",
                    "-v",
                    "--volume",
                    "--network",
                    "-p",
                    "--publish",
                },
            )
            return after[1:]  # drop the container/service name
    return None


def check_shell(command: str, ctx: Context) -> Block | None:
    if ctx.depth > MAX_DEPTH:
        return Block("The command is nested too deeply to check safely.")
    body_free, bodies = split_heredocs(command)
    for match in SUBST_RE.finditer(body_free):
        if block := check_shell(match.group(1) or match.group(2) or "", deeper(ctx)):
            return block
    for segment in split_segments(body_free):
        if block := check_tokens(strip_wrappers(tokenize(segment)), segment, ctx):
            return block
    for header, body in bodies:
        tokens = strip_wrappers(tokenize(header.split("<<")[0]))
        name = prog(tokens[0]) if tokens else ""
        inner = inner_command(name, tokens[1:]) if tokens else None
        if inner:
            name = prog(inner[0]) if inner else name
        if name in SHELLS and (block := check_shell(body, deeper(ctx))):
            return block
        if name in INTERPRETERS | DB_CLIENTS and (block := check_code(body, name)):
            return block
    return None


def deeper(ctx: Context) -> Context:
    return Context(cwd=ctx.cwd, depth=ctx.depth + 1, seen=ctx.seen)


def check_tokens(tokens: list[str], segment: str, ctx: Context) -> Block | None:
    if not tokens:
        return None
    name, args = prog(tokens[0]), tokens[1:]
    lower = [a.lower() for a in args]

    if name in SHELLS:
        for flag in ("-c", "-command", "/c", "-encodedcommand", "-enc", "-e"):
            if flag in lower:
                if flag in ("-encodedcommand", "-enc") or (
                    flag == "-e" and name in ("pwsh", "powershell")
                ):
                    return Block("Encoded PowerShell commands cannot be checked and are blocked.")
                if flag == "-e":
                    continue
                return check_shell(" ".join(args[lower.index(flag) + 1 :]), deeper(ctx))

    for check in (check_paths, check_rm, check_git, check_sql, check_docker, check_secrets):
        if block := check(name, args, lower, segment, ctx):
            return block

    inner = inner_command(name, args)
    if inner:
        return check_tokens(strip_wrappers(inner), " ".join(inner), deeper(ctx))
    return None


def check_code(code: str, interpreter: str) -> Block | None:
    """Inline scripts (`python -c`, heredoc to `python -`, `psql -c`)."""
    for match in ENV_IN_CODE.finditer(code):
        if is_env_file(match.group(1)):
            return env_block(match.group(1))
    if interpreter in DB_CLIENTS | INTERPRETERS and (sql := SQL_RE.search(code)):
        return sql_block(sql.group(0))
    if re.search(r"os\.environ|getenv|process\.env|ENV\[|\$ENV", code) and re.search(
        r"print|console\.log|puts|echo|write", code
    ):
        for name in re.findall(r"[A-Z][A-Z0-9_]{2,}", code):
            if SECRET_NAME.search(name):
                return Block(f"Printing the secret environment variable {name} is blocked.")
    return None


def check_paths(name, args, lower, segment, ctx) -> Block | None:
    git_rest = skip_options(args, {"-C", "-c"}) if name == "git" else []
    if git_rest and git_rest[0] in GIT_PATH_ONLY:
        return None  # e.g. `git check-ignore .env`, `git commit -m "... .env ..."`
    for token in args:
        if " " in token:
            continue  # a quoted sentence (message, description), not a path
        for piece in re.split(r"[=<>,:]", token):
            if piece and is_env_file(piece):
                return env_block(piece)
    if name in INTERPRETERS:
        for i, a in enumerate(lower):
            if (
                a in ("-c", "-e", "--eval", "-p")
                and i + 1 < len(args)
                and (block := check_code(args[i + 1], name))
            ):
                return block
    return None


def check_rm(name, args, lower, segment, ctx) -> Block | None:
    tokens = [name, *args]
    for i, tok in enumerate(tokens):
        if prog(tok) != "rm":
            continue
        recursive = force = False
        for arg in tokens[i + 1 :]:
            if arg == "--" or not arg.startswith("-"):
                continue
            if arg == "--recursive":
                recursive = True
            elif arg == "--force":
                force = True
            elif not arg.startswith("--"):
                recursive |= "r" in arg or "R" in arg
                force |= "f" in arg
        if recursive and force:
            return Block("`rm -rf` is blocked. Delete specific files, or ask the human to run it.")
    if name in ("remove-item", "ri", "rd", "rmdir", "del", "erase", "rm"):
        recursive = any(f.startswith("-rec") for f in lower)
        force = any(f.startswith("-fo") for f in lower)
        if recursive and force:
            return Block("`Remove-Item -Recurse -Force` is blocked. Ask the human to run it.")
    return None


def current_branch(cwd: str | None) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            cwd=cwd or None,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout.strip() or None) if result.returncode == 0 else None


def check_git(name, args, lower, segment, ctx) -> Block | None:
    if name != "git":
        return None
    rest = skip_options(args, {"-C", "-c", "--git-dir", "--work-tree"})
    if not rest:
        return None
    sub, rest = rest[0], rest[1:]
    if sub == "reset" and "--hard" in rest:
        return Block("`git reset --hard` discards work and is blocked. Use `git stash`, or ask.")
    if sub != "push":
        return None
    for a in rest:
        if (
            a in ("--force", "--force-with-lease", "--force-if-includes", "--mirror")
            or a.startswith("--force-with-lease=")
            or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a)
        ):
            return Block(
                "Force pushes are blocked (`git push --force/-f`). Push a new commit "
                "or ask the human."
            )
    if "--all" in rest:
        return Block("`git push --all` can update main and is blocked.")
    positional = skip_options_all(rest)
    for ref in positional[1:]:  # positional[0] is the remote
        if ref.startswith("+"):
            return Block(f"Force pushes are blocked (refspec '{ref}').")
        target = ref.split(":")[-1]
        if target in (MAIN_BRANCH, f"refs/heads/{MAIN_BRANCH}") or (
            target == "HEAD" and current_branch(ctx.cwd) == MAIN_BRANCH
        ):
            return main_block()
    if len(positional) <= 1 and current_branch(ctx.cwd) == MAIN_BRANCH:
        return main_block()
    return None


def skip_options_all(tokens: list[str]) -> list[str]:
    value_flags = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
    out, i = [], 0
    while i < len(tokens):
        if tokens[i] in value_flags:
            i += 2
        elif tokens[i].startswith("-"):
            i += 1
        else:
            out.append(tokens[i])
            i += 1
    return out


def main_block() -> Block:
    return Block(
        f"Pushing to `{MAIN_BRANCH}` is blocked: main changes only through a reviewed PR that a "
        "human merges (branch protection). Push a feature branch and open a PR."
    )


def sql_block(statement: str) -> Block:
    return Block(
        f"Destructive SQL (`{statement}`) is blocked. Schema changes go through Alembic "
        "migrations; integration tests reset their own *_test database."
    )


def check_sql(name, args, lower, segment, ctx) -> Block | None:
    if name in DB_CLIENTS:
        for a in args:
            if match := SQL_RE.search(a):
                return sql_block(match.group(0))
    return None


def check_docker(name, args, lower, segment, ctx) -> Block | None:
    if name not in ("docker", "podman"):
        return None
    words = [a for a in lower if not a.startswith("-")]
    if words[:2] == ["system", "prune"]:
        return Block("`docker system prune` deletes images, containers and volumes; blocked.")
    if words[:1] == ["volume"] and len(words) > 1 and words[1] in ("rm", "remove", "prune"):
        return Block("Removing Docker volumes deletes the database; blocked. Ask the human.")
    if words[:2] == ["compose", "config"] and not {"--quiet", "-q"} & set(lower):
        return Block(
            "`docker compose config` prints resolved environment values (STAFF_TOKEN "
            "from .env). Use `docker compose config --quiet` to validate."
        )
    if words[:1] == ["inspect"] or words[:2] in (["container", "inspect"], ["compose", "inspect"]):
        fmt = next((args[i + 1] for i, a in enumerate(lower[:-1]) if a in ("-f", "--format")), "")
        if not fmt or "env" in fmt.lower() or re.search(r"\{\{\s*(json\s+)?\.Config\s*\}\}", fmt):
            return Block(
                "`docker inspect` prints the container environment (secrets). Use a "
                "--format that selects other fields, e.g. '{{.State.Health.Status}}'."
            )
    return None


def check_secrets(name, args, lower, segment, ctx) -> Block | None:
    whole = VAR_REF.fullmatch(segment.strip().strip('"'))
    if whole and SECRET_NAME.search(whole.group(1) or whole.group(2) or ""):
        return Block("Evaluating a secret variable on its own prints it (PowerShell); blocked.")
    if name == "printenv":
        return Block("`printenv` prints environment secrets and is blocked.")
    if name == "env" and all(a.startswith("-") for a in args):
        return Block("`env` without a command lists environment variables (secrets); blocked.")
    if name == "set" and not args:
        return Block("`set` without arguments lists shell variables (secrets); blocked.")
    if name in ("export", "declare", "typeset") and (
        not args or lower in (["-p"], ["-x"], ["-px"])
    ):
        return Block(f"`{' '.join([name, *args])}` lists environment variables (secrets); blocked.")
    if name in ("get-childitem", "gci", "dir", "ls", "get-item", "gi") and any(
        a.lower().startswith("env:") for a in args
    ):
        return Block("Listing `env:` in PowerShell prints environment secrets and is blocked.")
    if name in PRINTERS or name in ("cat", "tee"):
        for var in VAR_REF.findall(segment):
            var_name = var[0] or var[1]
            if SECRET_NAME.search(var_name):
                return Block(
                    f"Printing ${var_name} is blocked: it is a secret. To check it is "
                    f'set, use `[ -n "${var_name}" ] && echo set`.'
                )
    return None


# --- Entry point ---------------------------------------------------------------------------


def evaluate(event: dict) -> Block | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    if tool in FILE_TOOLS:
        return check_file_tool(tool, tool_input)
    if tool in SHELL_TOOLS and isinstance(command := tool_input.get("command"), str):
        return check_shell(command, Context(cwd=event.get("cwd")))
    return None


def deny_json(reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"BenchTrack guard: {reason}",
            }
        }
    )


def main() -> int:
    try:
        block = evaluate(json.load(sys.stdin))
    except Exception as exc:  # fail closed: an event we cannot read is not let through
        print(
            f"BenchTrack guard could not check this tool call ({type(exc).__name__}); refusing it.",
            file=sys.stderr,
        )
        return 2
    if block:
        print(deny_json(block.reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
