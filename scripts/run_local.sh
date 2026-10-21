#!/usr/bin/env bash
# Run the runtime server locally on :8080 using .env, then in another shell:
#   curl -s localhost:8080/invocations -H 'content-type: application/json' \
#     -d '{"mode":"plan","repo":"owner/repo"}'
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [[ -f .env ]] && source .env; set +a
exec uv run python -m backlog_crew.app
