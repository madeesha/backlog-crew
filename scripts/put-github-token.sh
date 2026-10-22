#!/usr/bin/env bash
# Store (or rotate) the GitHub token in Secrets Manager without it touching shell history.
# Uses AWS_PROFILE / AWS_REGION / GITHUB_TOKEN_SECRET from deploy.env.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source deploy.env; set +a
AWS_REGION="${AWS_REGION:-$(aws configure get region --profile "$AWS_PROFILE")}"
secret="${GITHUB_TOKEN_SECRET:-backlog-crew/github}"

read -rsp "Paste the GitHub token (input hidden): " token; echo
[[ -n "$token" ]] || { echo "empty token"; exit 1; }
value=$(TOKEN="$token" python3 -c 'import json, os; print(json.dumps({"token": os.environ["TOKEN"]}))')

aws_args=(--profile "$AWS_PROFILE" --region "$AWS_REGION")
if aws secretsmanager describe-secret "${aws_args[@]}" --secret-id "$secret" >/dev/null 2>&1; then
  aws secretsmanager put-secret-value "${aws_args[@]}" --secret-id "$secret" --secret-string "$value" >/dev/null
  echo "Updated $secret in $AWS_REGION."
else
  aws secretsmanager create-secret "${aws_args[@]}" --name "$secret" \
    --description "GitHub token for backlog-crew" --secret-string "$value" >/dev/null
  echo "Created $secret in $AWS_REGION."
fi
