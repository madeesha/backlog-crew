import os
import sys
from pathlib import Path

import aws_cdk as cdk

sys.path.insert(0, str(Path(__file__).parent))
from stacks.crew_stack import BacklogCrewStack

app = cdk.App()
allowed_repos = app.node.try_get_context("allowedRepos") or ""
if not allowed_repos.strip():
    raise SystemExit(
        "Set allowedRepos, e.g. cdk deploy -c allowedRepos=owner/repo,owner/other "
        '(or "*" for every repo the GitHub token can reach).'
    )
BacklogCrewStack(
    app,
    "BacklogCrew",
    github_token_secret_name=app.node.try_get_context("githubTokenSecret") or "backlog-crew/github",
    allowed_repos=allowed_repos,
    model_id=app.node.try_get_context("modelId") or "global.anthropic.claude-opus-5-5",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
