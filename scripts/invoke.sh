#!/usr/bin/env bash
# Invoke the deployed runtime.
#   scripts/invoke.sh plan owner/repo
#   scripts/invoke.sh run  owner/repo 42
set -euo pipefail
RUNTIME_ARN="${RUNTIME_ARN:?set RUNTIME_ARN (CDK output BacklogCrew.RuntimeArn)}"
mode="${1:?usage: invoke.sh plan <owner/repo> | run <owner/repo> <issue>}"
repo="${2:?owner/repo required}"
suffix="$(date +%s)-$(openssl rand -hex 8)"
if [[ "$mode" == "run" ]]; then
  issue="${3:?issue number required}"
  payload="{\"mode\":\"run\",\"repo\":\"$repo\",\"issue\":$issue}"
  session="backlog-crew-issue-$issue-$suffix"
else
  payload="{\"mode\":\"plan\",\"repo\":\"$repo\"}"
  session="backlog-crew-plan-$suffix"
fi
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$session" \
  --payload "$payload" \
  --cli-binary-format raw-in-base64-out \
  /dev/stdout
echo
