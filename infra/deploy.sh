#!/usr/bin/env bash
# Deploy Runway to AWS, seed DynamoDB, and smoke-test the live API.
#
# Run from the repo root on a machine with AWS credentials (e.g. the workshop VS Code instance):
#   ./infra/deploy.sh                 # workshop defaults: bedrock-runtime + Haiku 4.5 inference profile
#   BEDROCK_ENDPOINT=mantle MODEL_FAST=anthropic.claude-haiku-5-5 MODEL_SMART=anthropic.claude-sonnet-5-5 ./infra/deploy.sh
#
# Re-running is safe: it updates the same stack and re-seeding just overwrites the demo rows.
# The API token is saved to .runway-token (git-ignored) so re-deploys keep the same one.
set -euo pipefail
cd "$(dirname "$0")/.."

STACK="${STACK:-runway}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
BEDROCK_ENDPOINT="${BEDROCK_ENDPOINT:-runtime}"
MODEL_FAST="${MODEL_FAST:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"
MODEL_SMART="${MODEL_SMART:-$MODEL_FAST}"
FOUNDER_NAME="${FOUNDER_NAME:-the founder}"
CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000}"

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "Checking tools and credentials"
command -v uv >/dev/null || die "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v aws >/dev/null || die "aws CLI not found"
aws sts get-caller-identity --region "$REGION" --query Arn --output text || die "No AWS credentials"
if command -v sam >/dev/null; then SAM=(sam); else SAM=(uvx --quiet --from aws-sam-cli sam); fi
# SAM needs a python3.12 on PATH to build for the python3.12 runtime.
if ! command -v python3.12 >/dev/null; then
  PYBIN="$(mktemp -d)"; ln -s "$(uv python find 3.12 2>/dev/null || (uv python install 3.12 >/dev/null && uv python find 3.12))" "$PYBIN/python3.12"
  export PATH="$PYBIN:$PATH"
fi

if [[ -f .runway-token ]]; then TOKEN="$(cat .runway-token)"; else
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"; echo "$TOKEN" > .runway-token; fi

say "Building (requirements → SAM)"
(cd backend && uv export --no-dev --no-hashes --no-emit-project -q -o requirements.txt)
(cd infra && "${SAM[@]}" build)

say "Deploying stack '$STACK' to $REGION (endpoint=$BEDROCK_ENDPOINT, models=$MODEL_FAST / $MODEL_SMART)"
(cd infra && "${SAM[@]}" deploy --stack-name "$STACK" --region "$REGION" --resolve-s3 \
  --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides \
    "ApiToken=$TOKEN" "BedrockEndpoint=$BEDROCK_ENDPOINT" "ModelFast=$MODEL_FAST" "ModelSmart=$MODEL_SMART" \
    "FounderName=$FOUNDER_NAME" "FounderPhone=${FOUNDER_PHONE:-}" "EmailFrom=${EMAIL_FROM:-}" \
    "BridgeUrl=${BRIDGE_URL:-}" "CorsOrigins=$CORS_ORIGINS")

out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
          --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
API="$(out ApiUrl)"; TABLE="$(out TableName)"

say "Seeding DynamoDB table $TABLE"
(cd backend && RUNWAY_STORE=dynamodb RUNWAY_DYNAMODB_TABLE="$TABLE" RUNWAY_AWS_REGION="$REGION" uv run python -m runway.seed)

say "Smoke test"
curl -fsS "$API/health"; echo
curl -fsS "$API/dashboard/metrics" -H "X-Runway-Token: $TOKEN"; echo
echo "Asking Claude a question through the live API (takes a few seconds)…"
curl -fsS "$API/ask" -H "X-Runway-Token: $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"which subscriptions renew in the next 30 days?"}'; echo

say "Done"
cat <<EOF
  API URL:   $API
  Token:     saved in .runway-token  (send as header X-Runway-Token)
  Table:     $TABLE
  Logs:      aws logs tail /aws/lambda/\$(aws cloudformation describe-stack-resource --stack-name $STACK --logical-resource-id ApiFunction --query StackResourceDetail.PhysicalResourceId --output text) --follow

  If /ask answered with a plain list instead of a friendly sentence, Claude fell back to templates:
  check the logs for "llm." warnings (usually model access or IAM).
EOF
