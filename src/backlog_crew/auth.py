"""Credentials for the agents.

- GitHub token (for git clone/push): AgentCore Identity API-key provider, or the
  GITHUB_TOKEN env var when running locally.
- Gateway calls: SigV4-signed with the runtime's IAM role (gateway uses AWS_IAM auth),
  so there is no gateway token to manage.
"""

import os

import boto3
import httpx
from bedrock_agentcore.identity.auth import requires_api_key
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from backlog_crew.config import settings


def github_token() -> str:
    if token := os.environ.get("GITHUB_TOKEN"):
        return token
    return _github_token_from_identity()


@requires_api_key(provider_name=settings().github_token_provider)
def _github_token_from_identity(*, api_key: str) -> str:
    return api_key


class SigV4HttpxAuth(httpx.Auth):
    """Signs each MCP HTTP request to AgentCore Gateway with the current AWS credentials."""

    requires_request_body = True

    def __init__(self, region: str, service: str = "bedrock-agentcore"):
        self._region = region
        self._service = service
        self._session = boto3.Session()

    def auth_flow(self, request: httpx.Request):
        credentials = self._session.get_credentials().get_frozen_credentials()
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
        )
        SigV4Auth(credentials, self._service, self._region).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers))
        yield request
