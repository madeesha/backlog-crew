import subprocess
from pathlib import Path

import pytest

from backlog_crew.tools.workspace import BASE_COMMANDS, Workspace, _guarded


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello")
    (tmp_path / "api").mkdir()
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return Workspace(root=tmp_path, repo="o/r", base_branch="main", branch="test")


def tool_named(tools, name):
    return next(t for t in tools if t.tool_name == name)


def test_resolve_blocks_escape(ws: Workspace):
    with pytest.raises(ValueError):
        ws.resolve("../outside.txt")


def test_refuses_unlisted_commands(ws: Workspace):
    assert _guarded("rm -rf /", ws.root, BASE_COMMANDS).startswith("refused")
    assert _guarded("npm test", ws.root, BASE_COMMANDS).startswith("refused")


def test_project_commands_are_allowed_after_allow(ws: Workspace):
    ws.allow({"npm"})
    assert "npm" in ws.allowed_commands


def test_refuses_git_push(ws: Workspace):
    assert "orchestrator" in _guarded("git push origin main", ws.root, BASE_COMMANDS)


def test_read_only_by_default(ws: Workspace):
    assert "write_file" not in {t.tool_name for t in ws.tools()}


def test_write_scope_is_enforced(ws: Workspace):
    write = tool_named(ws.tools(write_scope="api"), "write_file")
    assert write(path="api/a.txt", content="x").startswith("wrote")
    assert write(path="README.md", content="x").startswith("refused")
    assert (ws.root / "README.md").read_text() == "hello"


def test_allowed_command_runs(ws: Workspace):
    assert "README.md" in _guarded("ls", ws.root, BASE_COMMANDS)
