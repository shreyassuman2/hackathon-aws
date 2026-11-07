# Deploying to AWS

## Fast path (workshop account)

On a machine with AWS credentials (the workshop VS Code instance), from the repo root:

```bash
./infra/deploy.sh
```

It builds, deploys the stack, seeds DynamoDB, and smoke-tests the live API, including one real
Claude call. Defaults match the workshop account (`bedrock-runtime` + the Haiku 4.5 inference
profile). The API token is saved to `.runway-token`. If the deploy fails creating `RunwayRole`,
the workshop role probably isn't allowed to create IAM roles; ask the organizers which role to use.

The manual steps below explain what the script does and how to deploy with other settings.

## Manual

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

## Live negotiation email

By default negotiations run in demo mode: emails print to the logs and the vendor's replies are
canned. To negotiate with a real inbox (a teammate playing the vendor):

1. **SES:** verify the sender (`EMAIL_FROM`) and the teammate's address. New accounts are in the
   SES sandbox, which only delivers to verified addresses. That's fine for a demo, and it's a second
   safety net.
2. **Reply inbox:** a Gmail account for Runway with 2-step verification on, and an
   [app password](https://myaccount.google.com/apppasswords) for IMAP.
3. **Deploy:**
   ```bash
   EMAIL_FROM=runway.demo@gmail.com \
   VENDOR_EMAIL_OVERRIDE=teammate@example.com \
   IMAP_USER=runway.demo@gmail.com IMAP_PASSWORD='abcd efgh ijkl mnop' \
   ./infra/deploy.sh
   ```
   **Always set `VENDOR_EMAIL_OVERRIDE` for demos.** With it, every vendor email goes to the teammate
   no matter which vendor is being negotiated. Without it, Runway only emails vendors whose address
   was given explicitly (`POST /negotiations {"vendor_email": ...}`). A negotiation started from a
   text ("y", "negotiate Cursor") runs in demo mode rather than emailing a guessed address like
   `renewals@cursor.com`, which is a real company.
4. **Replies:** the teammate replies to Runway's email and keeps the subject line (`Re: Cursor renewal: pricing`).
   The worker Lambda checks the inbox every 5 minutes. To move faster in a live demo, trigger a step
   right after the reply: `POST /negotiations/{id}/tick` (or run `make worker` locally, which checks every 10 seconds).

The IMAP app password is stored as a Lambda environment variable (hidden in the deploy, but readable
by anyone with Lambda console access to the account). Use a throwaway Gmail account, not a personal one.
