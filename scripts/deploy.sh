#!/usr/bin/env bash
# Deploy (or update) the crew with the settings in deploy.env.
#   scripts/deploy.sh          deploy
#   scripts/deploy.sh diff     show what would change
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f deploy.env ]] || { echo "deploy.env not found: cp deploy.env.example deploy.env and fill it in"; exit 1; }
set -a; source deploy.env; set +a
: "${AWS_PROFILE:?set AWS_PROFILE in deploy.env}"
: "${ALLOWED_REPOS:?set ALLOWED_REPOS in deploy.env}"
export AWS_REGION="${AWS_REGION:-$(aws configure get region --profile "$AWS_PROFILE")}"
export CDK_DEFAULT_REGION="$AWS_REGION"

echo "==> Checking AWS credentials ($AWS_PROFILE, $AWS_REGION)"
if ! account=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text 2>/dev/null); then
  echo "Not logged in. Run: aws sso login --profile $AWS_PROFILE"; exit 1
fi
export CDK_DEFAULT_ACCOUNT="$account"
echo "    account $account"

echo "==> Checking the GitHub token secret ($GITHUB_TOKEN_SECRET)"
if ! aws secretsmanager describe-secret --profile "$AWS_PROFILE" --region "$AWS_REGION" \
     --secret-id "$GITHUB_TOKEN_SECRET" >/dev/null 2>&1; then
  echo "Secret not found. Run: scripts/put-github-token.sh"; exit 1
fi

echo "==> Checking Docker can build linux/arm64 (AgentCore runs arm64)"
if ! docker buildx inspect 2>/dev/null | grep -q "linux/arm64"; then
  cat <<'MSG'
Docker can't build arm64 images on this machine yet. Install QEMU emulation once:
  docker run --privileged --rm tonistiigi/binfmt --install arm64
then run this script again. (Builds under emulation are slower; that's expected.)
MSG
  exit 1
fi

if ! aws cloudformation describe-stacks --profile "$AWS_PROFILE" --region "$AWS_REGION" \
     --stack-name CDKToolkit >/dev/null 2>&1; then
  echo "==> Bootstrapping CDK in $account/$AWS_REGION (first deploy only)"
  cdk bootstrap "aws://$account/$AWS_REGION" --profile "$AWS_PROFILE"
fi

uv sync -q --extra infra
args=(--profile "$AWS_PROFILE"
      -c "allowedRepos=$ALLOWED_REPOS"
      -c "modelId=${MODEL_ID:-global.anthropic.claude-opus-5-5}"
      -c "githubTokenSecret=$GITHUB_TOKEN_SECRET")

if [[ "${1:-}" == "diff" ]]; then
  cdk diff "${args[@]}"
else
  echo "==> Deploying"
  cdk deploy "${args[@]}" --require-approval broadening --outputs-file cdk-outputs.json
  echo
  echo "Done. Outputs (also in cdk-outputs.json):"
  python3 -c "import json; [print(f'  {k}: {v}') for k, v in json.load(open('cdk-outputs.json'))['BacklogCrew'].items()]"
fi
