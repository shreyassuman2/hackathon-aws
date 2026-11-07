# Deploying to AWS

Prereqs: AWS account, [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), credentials configured (`aws configure` or `AWS_PROFILE`).

1. **Bedrock model access.** In the Bedrock console → Model access, check access for
   `anthropic.claude-haiku-5-5` and `anthropic.claude-sonnet-5-5`. If they aren't available on your
   account yet, deploy with `ModelFast=anthropic.claude-haiku-4-5` and `ModelSmart=anthropic.claude-sonnet-5`
   (open to all accounts).
2. **SES (optional, for live negotiation email).** Verify a sender address or domain in SES. New
   accounts are in the SES sandbox, which can only send to verified addresses. That's fine for a
   demo where a teammate plays the vendor.
3. **Deploy.**
   ```bash
   make deploy            # = make requirements && cd infra && sam build && sam deploy --guided
   ```
   Pick a region where Claude on Bedrock is available (e.g. `us-east-1`). For `ApiToken` use
   `openssl rand -hex 24`. Save the guided answers so later deploys are just `sam deploy`.
4. **Seed DynamoDB** from your laptop using the `TableName` output:
   ```bash
   cd backend && RUNWAY_STORE=dynamodb RUNWAY_DYNAMODB_TABLE=<TableName> uv run python -m runway.seed
   ```
5. **Smoke test** with the `ApiUrl` output:
   ```bash
   curl $API/health
   curl $API/dashboard/metrics -H "X-Runway-Token: $TOKEN"
   ```
6. **Point clients at it.** Frontend: `VITE_RUNWAY_API_URL`, `VITE_RUNWAY_TOKEN`. Bridge:
   `RUNWAY_API_URL`, `RUNWAY_API_TOKEN`. Emulator: `index.html?api=$API&token=$TOKEN`.

## Notes

- Every route but `/health` requires `X-Runway-Token`. The API can approve spending, so don't
  deploy without it (the template enforces a 16+ character token).
- `VITE_RUNWAY_TOKEN` ends up in the browser bundle. That's acceptable for a hackathon demo but not
  for production; put real auth (e.g. Cognito) in front before real users.
- Logs: CloudWatch → `/aws/lambda/<stack>-ApiFunction-…` and `…-NegotiationFunction-…`.
- Teardown: `sam delete`. The DynamoDB table is retained on purpose; delete it by hand if you mean to.
