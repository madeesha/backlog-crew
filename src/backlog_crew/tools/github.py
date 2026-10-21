"""GitHub access through AgentCore Gateway (MCP).

The gateway fronts GitHub's MCP server as a target named `github`, so tools arrive as
`github___<tool>`. Each agent gets only the tools in its allowlist.

GitHub's MCP server has renamed tools between releases (e.g. `get_issue` -> `issue_read`),
so the lists below include both spellings. Run `scripts/list_gateway_tools.py` to see
the names your gateway actually exposes and trim these lists to match.
"""

import re

from strands.tools.mcp import MCPClient

from backlog_crew.auth import SigV4HttpxAuth
from backlog_crew.config import settings

READ_TOOLS = {
    "list_issues",
    "search_issues",
    "get_issue",
    "issue_read",
    "get_issue_comments",
    "list_pull_requests",
    "get_pull_request",
    "pull_request_read",
    "list_label",
    "get_label",
}

PLANNER_TOOLS = READ_TOOLS | {"create_issue", "issue_write", "add_issue_comment"}

ORCHESTRATOR_TOOLS = READ_TOOLS | {
    "update_issue",
    "issue_write",
    "add_issue_comment",
    "create_pull_request",
}


def github_mcp_client(allowed_tools: set[str]) -> MCPClient:
    s = settings()
    if not s.gateway_url:
        raise RuntimeError("GATEWAY_URL is not set")
    names = "|".join(sorted(re.escape(t) for t in allowed_tools))
    pattern = re.compile(rf"^{re.escape(s.github_target_prefix)}___({names})$")
    return MCPClient(
        url=s.gateway_url,
        auth_provider=SigV4HttpxAuth(region=s.aws_region),
        tool_filters={"allowed": [pattern]},
    )
