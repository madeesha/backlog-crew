from strands import Agent

from backlog_crew.agents import prompts
from backlog_crew.model import make_model
from backlog_crew.project import ProjectConfig
from backlog_crew.tools.github import PLANNER_TOOLS, github_mcp_client
from backlog_crew.tools.workspace import Workspace


def run_planner(repo: str) -> dict:
    """Compare the repo's product spec with its default branch; propose `proposed` issues."""
    ws = Workspace.clone(repo)
    project = ProjectConfig.load(ws.root)
    system_prompt = prompts.PLANNER.format(
        repo=repo,
        project=project.context(),
        spec=project.spec,
        max_issues=project.max_issues,
    )
    agent = Agent(
        name="planner",
        model=make_model("planner"),
        system_prompt=system_prompt,
        tools=[*ws.tools(), github_mcp_client(PLANNER_TOOLS)],
        callback_handler=None,
    )
    result = agent("Review the backlog against the product spec.")
    return {"repo": repo, "result": str(result)}
