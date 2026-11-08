# Runway

**An AI finance team for startups that lives in iMessage. Built on AWS.**

Runway watches a startup's card spend, AI API usage and SaaS subscriptions, finds waste, and acts
after one tap of approval. It negotiates renewals by email on its own, across days, and texts
the founder when it's done: *"Closed Cursor at 22% off. $3,696/yr saved."*

| Pillar | What it catches |
|---|---|
| 🤖 **AI spend** | Week-over-week spikes, expensive models doing cheap work, forgotten batch jobs |
| 📦 **SaaS sprawl** | Dormant seats, overlapping tools, unused add-ons, shadow IT, upcoming renewals (then negotiates them) |
| 💳 **Compliance** | Card swipes over cap, missing memos, red-flag merchants. Asks the employee before bothering the founder |

## Quick start (no AWS account needed)

Needs [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
make setup      # installs Python + Node deps, creates .env
make seed       # loads the Acme Labs demo company
make api        # http://localhost:8000/docs
```

In a second terminal, play the founder:

```bash
curl -s localhost:8000/transactions -H 'content-type: application/json' \
  -d '{"merchant":"Cursor","amount":1400}' | jq .alert.message
curl -s localhost:8000/imessage/inbound -H 'content-type: application/json' -d '{"text":"y"}'
make worker     # negotiation runs; watch the emails and texts print in the terminal
```

By default everything is local: data in `backend/.data/runway.json`, texts and emails printed
to the console, Claude off (deterministic templates). Turn pieces on in `.env`:

| Want | Set |
|---|---|
| Claude (Bedrock) | `RUNWAY_LLM=bedrock` + AWS credentials |
| DynamoDB | `RUNWAY_STORE=dynamodb` |
| Real iMessages | `RUNWAY_NOTIFIER=imessage` + `make bridge` on a Mac |
| Real vendor email | `RUNWAY_MAIL=live` + SES sender + IMAP inbox |

Other tools: `make frontend` (dashboard on :3000), `make emulator` (card-swipe page), `make test`.

## How it fits together

```
 card swipe / bank feed ──▶ POST /transactions ──▶ pipeline
                                                    │ router (known vendors → Claude Haiku)
                                                    │ policies (auto-cancel, auto-approve…)
                                                    │ specialist agent (Claude Sonnet)
                                                    ▼
                                          alert ─▶ restraint filter ─▶ iMessage (now / business hours / digest)
                                                    │
 founder texts "y" ──▶ POST /imessage/inbound ──▶ conversation ─▶ approve → start negotiation
                                                                ─▶ question → Ask-Anything (Claude + tools)
                                                                ─▶ command → "cancel Notion", "show pending"

 negotiation worker (local loop or Lambda every 5 min)
   tick: poll inbox → classify reply → decide → queue email+text → one atomic state write → send
```

All state lives in one DynamoDB table (or the local JSON file). See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [docs/DEPLOY.md](docs/DEPLOY.md)
to put it on AWS.

## Repo layout

```
backend/            Python 3.12 · FastAPI · uv
  runway/
    api.py            HTTP routes
    pipeline.py       transaction → finding → alert
    conversation.py   inbound iMessage routing (Y/N, commands, questions)
    agents/           router, ai_spend, saas, compliance, ask, commands
    negotiation/      engine (state machine), reasoner, mail, worker, fixtures
    policies.py       founder rules that allow autonomous action
    restraint.py      when to interrupt the founder
    alerts.py · messaging.py · employees.py · digest.py
    llm.py            the only module that talks to Claude (Bedrock)
    store.py          DynamoDB / local-file persistence
    seed/demo.json    Acme Labs demo data
  tests/
bridge/             Node: Mac Messages ⇄ API
frontend/           Vite dashboard (to be redesigned)
tools/purchase-emulator/   card-swipe page for demos
infra/template.yaml AWS SAM: API Lambda, worker Lambda, digest Lambda, DynamoDB
```

## Team

Four owners, one area each. See [CONTRIBUTING.md](CONTRIBUTING.md).

