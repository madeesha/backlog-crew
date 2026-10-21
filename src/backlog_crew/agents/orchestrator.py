from strands import Agent, tool

from backlog_crew.agents import prompts
from backlog_crew.agents.specialists import specialist_tools
from backlog_crew.config import settings
from backlog_crew.model import make_model
from backlog_crew.project import ProjectConfig
from backlog_crew.tools.github import ORCHESTRATOR_TOOLS, github_mcp_client
from backlog_crew.tools.workspace import Workspace


def run_orchestrator(repo: str, issue_number: int) -> dict:
    """Take one `agent-ready` issue to a pull request (or to NEEDS_HUMAN)."""
    ws = Workspace.clone(repo, branch=f"backlog-crew/issue-{issue_number}")
    project = ProjectConfig.load(ws.root)
    ws.allow(project.command_names())

    @tool
    def commit_and_push(message: str) -> str:
        """Commit every change on the work branch and push it. Call once, after the reviewer
        approves. `message` is the commit message, e.g. `Add CSV export (#42)`."""
        if not ws.has_changes():
            return "nothing to commit"
        return ws.commit_and_push(message)

    has_checks = bool(project.integration_checks)
    system_prompt = prompts.ORCHESTRATOR.format(
        repo=repo,
        branch=ws.branch,
        base=ws.base_branch,
        project=project.context(),
        integration_tool="integration_check, " if has_checks else "",
        integration_step=(
            "If more than one connected area changed, run integration_check. " if has_checks else ""
        ),
        max_rounds=settings().max_review_rounds,
    )
    agent = Agent(
        name="orchestrator",
        model=make_model("orchestrator"),
        system_prompt=system_prompt,
        tools=[
            *specialist_tools(ws, project),
            commit_and_push,
            *ws.tools(),
            github_mcp_client(ORCHESTRATOR_TOOLS),
        ],
        callback_handler=None,
    )
    result = agent(f"Work on issue #{issue_number}.")
    return {"repo": repo, "issue": issue_number, "branch": ws.branch, "result": str(result)}
