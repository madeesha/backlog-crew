"""Deployment settings, read once from environment variables.

These describe where the crew runs, not what it works on. Everything about a target
repository comes from that repository's `.backlog-crew.yaml` (see project.py).
"""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    aws_region: str
    default_model_id: str
    allowed_repos: frozenset[str]
    gateway_url: str
    github_target_prefix: str
    github_token_provider: str
    workspace_root: str
    max_review_rounds: int

    def model_id_for(self, agent_name: str) -> str:
        """Per-agent override via MODEL_ID_<AGENT>, e.g. MODEL_ID_REVIEWER."""
        return os.environ.get(f"MODEL_ID_{agent_name.upper()}", self.default_model_id)

    def repo_allowed(self, repo: str) -> bool:
        return "*" in self.allowed_repos or repo.lower() in self.allowed_repos


@lru_cache
def settings() -> Settings:
    allowed = os.environ.get("ALLOWED_REPOS", "")
    return Settings(
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        # Bedrock model / inference-profile id. Confirm the exact id enabled in your
        # account in the Bedrock console (Model access / Cross-region inference).
        default_model_id=os.environ.get("MODEL_ID", "global.anthropic.claude-opus-5-5"),
        # Comma-separated owner/name list, or "*" for any repo the GitHub token can reach.
        allowed_repos=frozenset(r.strip().lower() for r in allowed.split(",") if r.strip()),
        gateway_url=os.environ.get("GATEWAY_URL", ""),
        github_target_prefix=os.environ.get("GITHUB_TARGET_PREFIX", "github"),
        github_token_provider=os.environ.get("GITHUB_TOKEN_PROVIDER", "backlog-crew-github-token"),
        workspace_root=os.environ.get("WORKSPACE_ROOT", "/tmp/workspaces"),
        max_review_rounds=int(os.environ.get("MAX_REVIEW_ROUNDS", "2")),
    )
