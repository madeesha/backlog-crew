"""AgentCore Runtime entrypoint.

Payloads:
  {"mode": "plan", "repo": "owner/name"}               -> planner proposes backlog issues
  {"mode": "run",  "repo": "owner/name", "issue": 42}  -> orchestrator takes #42 to a PR

The repo must be in ALLOWED_REPOS and have a `.backlog-crew.yaml` at its root.

A run can take longer than one invocation should block for, so the work runs in a
background task and the invocation returns at once. `@app.async_task` keeps the session's
ping status HEALTHY_BUSY while it runs so AgentCore doesn't reap it. Results land on GitHub
(issues, PRs, comments) and in the CloudWatch logs.
"""

import asyncio
import logging
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from backlog_crew.agents.orchestrator import run_orchestrator
from backlog_crew.agents.planner import run_planner
from backlog_crew.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backlog_crew")

REPO_PATTERN = re.compile(r"^[\w-][\w.-]*/[\w-][\w.-]*$")

app = BedrockAgentCoreApp()
_running: set[asyncio.Task] = set()  # keep references so tasks aren't garbage-collected


@app.async_task
async def _background(mode: str, repo: str, issue: int | None) -> None:
    try:
        if mode == "plan":
            result = await asyncio.to_thread(run_planner, repo)
        else:
            result = await asyncio.to_thread(run_orchestrator, repo, issue)
        log.info("finished %s for %s: %s", mode, repo, result)
    except Exception:
        log.exception("%s for %s failed", mode, repo)


def validate(payload: dict) -> str | None:
    """Return an error message, or None if the payload is acceptable."""
    mode, repo, issue = payload.get("mode"), payload.get("repo"), payload.get("issue")
    if mode not in {"plan", "run"}:
        return "mode must be 'plan' or 'run'"
    if not isinstance(repo, str) or not REPO_PATTERN.match(repo):
        return "repo must be 'owner/name'"
    if not settings().repo_allowed(repo):
        return f"{repo} is not in ALLOWED_REPOS"
    if mode == "run" and not isinstance(issue, int):
        return "'run' needs an integer 'issue'"
    return None


@app.entrypoint
async def invoke(payload: dict) -> dict:
    if error := validate(payload):
        return {"error": error}
    mode, repo, issue = payload["mode"], payload["repo"], payload.get("issue")
    task = asyncio.create_task(_background(mode, repo, issue))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return {"accepted": True, "mode": mode, "repo": repo, "issue": issue}


if __name__ == "__main__":
    app.run()
