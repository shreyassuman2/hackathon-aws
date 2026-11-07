# Architecture

## Principles

1. **One-tap approval.** Anything that moves money waits for the founder's Y, unless a policy the
   founder set (`policies.py`) explicitly allows it, and those actions are always reported and undoable.
2. **Restraint.** Every finding gets a tier (`restraint.py`): *urgent* texts now, *decision_needed*
   waits for business hours, *informational* goes in the Monday/Friday digest.
3. **Claude is an upgrade, never a dependency.** Every LLM call in `llm.py` returns `None` on
   failure, refusal or when `RUNWAY_LLM=off`, and every caller has a deterministic fallback. The
   demo works with zero credentials.
4. **Real numbers only.** Prompts receive the data rows and are told not to invent figures.

## Models

| Tier | Default (Bedrock ID) | Used for |
|---|---|---|
| fast | `anthropic.claude-haiku-5-5` | routing unknown merchants, classifying vendor replies, parsing commands |
| smart | `anthropic.claude-sonnet-5-5` | alert copy, negotiation emails, Ask-Anything tool use |

Calls use the Anthropic SDK's `AsyncAnthropicBedrockMantle` client (Messages API on Bedrock).
Structured outputs (`messages.parse` + Pydantic) replace "please return JSON" prompting.

## Storage

One DynamoDB table, `pk = CO#<company>`, `sk = <entity>#<id>`. Every read is a partition query
with `begins_with`; filtering happens in Python. That's plenty at startup scale; add a GSI when a
list gets large. `LocalStore` mirrors the same interface in a JSON file for dev and tests.

`update(..., expect_version=n)` is an optimistic lock (a DynamoDB condition expression). The
negotiation engine relies on it.

## Negotiation engine (`negotiation/engine.py`)

The old version spawned one OS process per deal and tracked PIDs. Now a deal is just a record and
`tick(id)` moves it forward one step:

```
opening → waiting ⇄ (reply → classify → decide → counter) → closed_won | closed_lost | stalled
                     └─ final offer / too many rounds → needs_founder → (Y/N) → won/lost
```

- **Atomic steps:** a tick computes the new state and writes it in one versioned update.
- **Transactional outbox:** emails, texts and side-records are queued in that same write, then
  delivered by `_flush`. A crash between commit and send leaves them queued for the next tick.
- **Replay-safe inbox:** demo replies are read by `inbox_cursor` and live replies are de-duplicated
  by `seen_refs`, both persisted with the state. IMAP messages are only marked read after the commit.
- **Pure strategy:** `reasoner.decide()` has no I/O; the concession curve and escalation rules are unit-tested.

Runs anywhere: `make worker` locally, a scheduled Lambda in AWS, or `POST /negotiations/{id}/tick`.

## AWS deployment (`infra/template.yaml`)

| Resource | Purpose |
|---|---|
| `ApiFunction` (Lambda + HTTP API) | FastAPI via Mangum |
| `NegotiationFunction` (every 5 min) | `tick_all()` + deliver held alerts once business hours start |
| `DigestFunction` (Mon 8am, Fri 4pm PT) | Digest of held items |
| `Table` (DynamoDB, on-demand, PITR) | All data |
| IAM | `bedrock-mantle:CreateInference`, `ses:SendEmail`, table CRUD |

The iMessage bridge can't run in AWS (iMessage needs a Mac). Expose it with a tunnel and set
`BridgeUrl`, or leave messaging on `console` and use CloudWatch logs.

## What changed from LEGR

| LEGR | Runway |
|---|---|
| Dedalus agents + runner | Claude on Bedrock via `llm.py` |
| Supabase Postgres + Realtime listener | DynamoDB (or local file); webhook calls the pipeline directly; dashboard polls |
| Subprocess "Machines" + PID registry + JSON files | Store-backed state machine, scheduled tick |
| `flux_query` RPC running LLM-generated SQL | Read-only query tools for Claude |
| pgvector long-term memory (OpenAI embeddings) | Dropped for now; chat history kept (stretch goal) |
| `negotiation_sm.py` **and** `machine/` (two negotiation systems) | One engine |
| "email the team" command | Dropped (it never sent anything) |

Bugs fixed in the rewrite: approving a negotiation alert failed (insert used columns that didn't
exist); cancel/negotiate read non-existent price columns; demo replies replayed after a restart;
"…if you'd like to proceed" counted as acceptance; substring Y/N matching ("today" → yes);
compliance alerts could never be urgent; held business-hours alerts were never sent; founder vs.
employee detection broke on phone formatting; hardcoded Supabase key and a real phone number in
the repo.
