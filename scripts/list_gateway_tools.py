"""Print the tools the gateway exposes, to check the GitHub target works and to trim the
allowlists in src/backlog_crew/tools/github.py.

    GATEWAY_URL=https://... uv run python scripts/list_gateway_tools.py
"""

from strands.tools.mcp import MCPClient

from backlog_crew.auth import SigV4HttpxAuth
from backlog_crew.config import settings

s = settings()
client = MCPClient(url=s.gateway_url, auth_provider=SigV4HttpxAuth(region=s.aws_region))
with client:
    for t in sorted(client.list_tools_sync(), key=lambda t: t.tool_name):
        print(t.tool_name)
