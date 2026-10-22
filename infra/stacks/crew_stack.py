"""Everything the agents need on AWS:

- ECR image built from runtime/Dockerfile (arm64)
- AgentCore Identity API-key provider holding the GitHub token (read from Secrets Manager)
- AgentCore Gateway (MCP, AWS_IAM inbound auth) with GitHub's MCP server as a target
- AgentCore Runtime running backlog_crew.app, allowed to call Bedrock and the gateway
"""

from pathlib import Path

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GITHUB_MCP_ENDPOINT = "https://api.githubcopilot.com/mcp/"
GITHUB_TOKEN_PROVIDER = "backlog-crew-github-token"
GITHUB_TARGET_NAME = "github"


class BacklogCrewStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_token_secret_name: str,
        allowed_repos: str,
        model_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        image = ecr_assets.DockerImageAsset(
            self,
            "AgentImage",
            directory=str(PROJECT_ROOT),
            file="runtime/Dockerfile",
            platform=ecr_assets.Platform.LINUX_ARM64,
            exclude=[".venv", "cdk.out", ".git", "**/__pycache__"],
        )

        # The secret is created by hand (see README) as JSON: {"token": "github_pat_..."}
        github_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "GithubTokenSecret", github_token_secret_name
        )
        github_key = agentcore.CfnApiKeyCredentialProvider(
            self,
            "GithubTokenProvider",
            name=GITHUB_TOKEN_PROVIDER,
            api_key_secret_source="EXTERNAL",
            api_key_secret_config=agentcore.CfnApiKeyCredentialProvider.SecretReferenceProperty(
                secret_id=github_token_secret_name, json_key="token"
            ),
        )

        identity_access = iam.PolicyStatement(
            actions=[
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                "bedrock-agentcore:GetResourceApiKey",
            ],
            resources=["*"],
        )

        gateway_role = iam.Role(
            self,
            "GatewayRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )
        gateway_role.add_to_policy(identity_access)
        github_secret.grant_read(gateway_role)

        gateway = agentcore.CfnGateway(
            self,
            "Gateway",
            name="backlog-crew-gateway",
            protocol_type="MCP",
            authorizer_type="AWS_IAM",
            role_arn=gateway_role.role_arn,
        )
        gateway.node.add_dependency(gateway_role)

        github_target = agentcore.CfnGatewayTarget(
            self,
            "GithubTarget",
            name=GITHUB_TARGET_NAME,
            gateway_identifier=gateway.attr_gateway_identifier,
            target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    mcp_server=agentcore.CfnGatewayTarget.McpServerTargetConfigurationProperty(
                        endpoint=GITHUB_MCP_ENDPOINT
                    )
                )
            ),
            credential_provider_configurations=[
                agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="API_KEY",
                    credential_provider=agentcore.CfnGatewayTarget.CredentialProviderProperty(
                        api_key_credential_provider=agentcore.CfnGatewayTarget.ApiKeyCredentialProviderProperty(
                            provider_arn=github_key.attr_credential_provider_arn,
                            credential_location="HEADER",
                            credential_parameter_name="Authorization",
                            # Check after the first deploy that GitHub receives
                            # "Bearer <token>" (scripts/list_gateway_tools.py fails with 401
                            # if not).
                            credential_prefix="Bearer ",
                        )
                    ),
                )
            ],
        )

        runtime_role = iam.Role(
            self,
            "RuntimeRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": self.account}},
            ),
        )
        image.repository.grant_pull(runtime_role)
        github_secret.grant_read(runtime_role)
        runtime_role.add_to_policy(identity_access)
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    # global.* inference profiles route to models with no region in the ARN
                    "arn:aws:bedrock:::foundation-model/*",
                    f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                ],
            )
        )
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeGateway"],
                resources=[gateway.attr_gateway_arn],
            )
        )
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                    "logs:DescribeLogGroups",
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "cloudwatch:PutMetricData",
                ],
                resources=["*"],
            )
        )

        runtime = agentcore.CfnRuntime(
            self,
            "Runtime",
            agent_runtime_name="backlog_crew",
            role_arn=runtime_role.role_arn,
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=agentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=image.image_uri
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC"
            ),
            protocol_configuration="HTTP",
            lifecycle_configuration=agentcore.CfnRuntime.LifecycleConfigurationProperty(
                idle_runtime_session_timeout=900,
                max_lifetime=8 * 60 * 60,
            ),
            environment_variables={
                "AWS_REGION": self.region,
                "MODEL_ID": model_id,
                "ALLOWED_REPOS": allowed_repos,
                "GATEWAY_URL": gateway.attr_gateway_url,
                "GITHUB_TARGET_PREFIX": GITHUB_TARGET_NAME,
                "GITHUB_TOKEN_PROVIDER": GITHUB_TOKEN_PROVIDER,
            },
        )
        runtime.node.add_dependency(runtime_role)
        runtime.node.add_dependency(github_target)

        CfnOutput(self, "RuntimeArn", value=runtime.attr_agent_runtime_arn)
        CfnOutput(self, "GatewayUrl", value=gateway.attr_gateway_url)
