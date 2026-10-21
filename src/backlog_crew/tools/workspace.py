"""A git checkout of the target repository that the agents work inside.

Agents never get a raw shell or push access: they get file tools and an allowlisted
command runner scoped to one checkout. Cloning, committing and pushing happen in code.
"""

import base64
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from strands import tool

from backlog_crew.auth import github_token
from backlog_crew.config import settings

# Inspection commands every agent may run. Each area's test command is added on top
# (see ProjectConfig.command_names), so a Go repo allows `go`, a Maven repo `./mvnw`, etc.
BASE_COMMANDS = {"git", "ls", "cat", "grep", "find", "head", "tail", "wc"}
BLOCKED_GIT = {"push", "remote", "config", "reset", "clean", "rebase", "checkout", "switch"}
COMMAND_TIMEOUT_S = 900
MAX_OUTPUT_CHARS = 20_000


def _git_auth_args() -> list[str]:
    # Token goes in a per-command header, never into .git/config or the remote URL.
    basic = base64.b64encode(f"x-access-token:{github_token()}".encode()).decode()
    return ["-c", f"http.extraheader=Authorization: Basic {basic}"]


def _run(args: list[str], cwd: Path, timeout: int = COMMAND_TIMEOUT_S) -> str:
    proc = subprocess.run(
        args, check=False, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    out = (proc.stdout + proc.stderr)[-MAX_OUTPUT_CHARS:]
    if proc.returncode != 0:
        return f"exit code {proc.returncode}\n{out}"
    return out or "(no output)"


@dataclass
class Workspace:
    root: Path
    repo: str
    base_branch: str
    branch: str
    allowed_commands: set[str] = field(default_factory=lambda: set(BASE_COMMANDS))

    @classmethod
    def clone(cls, repo: str, branch: str | None = None) -> "Workspace":
        """Fresh shallow clone of the repo's default branch; optionally create a work branch."""
        root = Path(settings().workspace_root) / repo.replace("/", "__") / (branch or "main-ro")
        if root.exists():
            shutil.rmtree(root)
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                *_git_auth_args(),
                "clone",
                "--depth",
                "50",
                f"https://github.com/{repo}.git",
                str(root),
            ],
            check=True,
            capture_output=True,
        )
        base = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root).strip()
        if branch:
            subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=root, check=True)
        return cls(root=root, repo=repo, base_branch=base, branch=branch or base)

    def allow(self, commands: set[str]) -> None:
        self.allowed_commands |= commands

    def resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escapes the workspace: {relative}")
        return path

    def has_changes(self) -> bool:
        return bool(_run(["git", "status", "--porcelain"], self.root).strip())

    def commit_and_push(self, message: str) -> str:
        _run(["git", "add", "-A"], self.root)
        commit = _run(
            [
                "git",
                "-c",
                "user.name=backlog-crew",
                "-c",
                "user.email=backlog-crew@users.noreply.github.com",
                "commit",
                "-m",
                message,
            ],
            self.root,
        )
        push = _run(["git", *_git_auth_args(), "push", "-u", "origin", self.branch], self.root)
        return f"{commit}\n{push}"

    def tools(self, write_scope: str | None = None) -> list:
        """Strands tools bound to this checkout.

        With `write_scope` (a directory relative to the repo root, "." for everything) the
        agent also gets write_file, limited to that directory. Without it, read-only.
        """
        ws = self

        @tool
        def read_file(path: str) -> str:
            """Read a text file from the repository. `path` is relative to the repo root."""
            return ws.resolve(path).read_text()[:MAX_OUTPUT_CHARS]

        @tool
        def list_files(path: str = ".") -> str:
            """List tracked files under a directory (relative to the repo root)."""
            return _run(["git", "ls-files", "--", str(ws.resolve(path))], ws.root)

        @tool
        def show_changes() -> str:
            """Show every change on this branch that isn't on the base branch yet, including
            new and uncommitted files, as a unified diff."""
            _run(["git", "add", "--intent-to-add", "--all"], ws.root)
            committed = _run(["git", "diff", f"origin/{ws.base_branch}...HEAD"], ws.root)
            working = _run(["git", "diff", "HEAD"], ws.root)
            return f"{committed}\n{working}"[:MAX_OUTPUT_CHARS]

        @tool
        def run_command(directory: str, command: str) -> str:
            """Run an allowed command inside `directory` (relative to the repo root, "." for the
            root), e.g. directory="backend", command="./mvnw -q test". Only the project's
            test commands and read-only tools (git, ls, cat, grep, find, head, tail, wc) are
            allowed; a refused command lists what is."""
            return _guarded(command, ws.resolve(directory), ws.allowed_commands)

        read_only = [read_file, list_files, show_changes, run_command]
        if write_scope is None:
            return read_only
        scope = ws.resolve(write_scope)

        @tool
        def write_file(path: str, content: str) -> str:
            """Create or overwrite a text file (relative to the repo root) with full content."""
            target = ws.resolve(path)
            if not target.is_relative_to(scope):
                return f"refused: you may only write under {write_scope}/"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return f"wrote {path} ({len(content)} chars)"

        return [*read_only, write_file]


def _guarded(command: str, cwd: Path, allowed: set[str]) -> str:
    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"refused: {e}"
    if not args or args[0] not in allowed:
        name = args[0] if args else ""
        return f"refused: '{name}' is not allowed. Allowed: {', '.join(sorted(allowed))}"
    if args[0] == "git" and len(args) > 1 and args[1] in BLOCKED_GIT:
        return f"refused: git {args[1]} is handled by the orchestrator, not agents"
    try:
        return _run(args, cwd)
    except subprocess.TimeoutExpired:
        return f"timed out after {COMMAND_TIMEOUT_S}s"
