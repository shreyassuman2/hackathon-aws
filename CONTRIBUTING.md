# Working on Runway

## Who owns what

All four of us work on the backend. Each area has one owner who reviews PRs touching it.
Fill in names/handles below. (Frontend comes later; see the end of this section.)

| # | Area | Owner | Files (under `backend/` unless noted) | Good first tasks |
|---|---|---|---|---|
| 1 | **Core & AWS** | _name_ | `runway/config.py`, `store.py`, `entities.py`, `models.py`, `llm.py`, `messaging.py`, `alerts.py`, `restraint.py`, `policies.py`, `seed.py`, `seed/`, `infra/`, repo setup | First `sam deploy`; seed DynamoDB; get a real Bedrock call working; add a GSI if a list gets slow |
| 2 | **Agents** | _name_ | `runway/persona.py`, `agents/` (except `commands.py`), `pipeline.py`, `employees.py` | Tune prompts with Bedrock on; more Ask-Anything tools; long-term memory (Bedrock embeddings) |
| 3 | **Negotiation** | _name_ | `runway/negotiation/` | Live email: SES inbound (receipt rule → S3 → Lambda) to replace IMAP; smarter concession strategy |
| 4 | **API & conversation** | _name_ | `runway/api.py`, `conversation.py`, `agents/commands.py`, `digest.py`, `handlers.py`, `bridge/` | Get the iMessage bridge running on the demo Mac; multi-alert replies ("Y to #2"); real auth |

**Frontend later:** `frontend/` and `tools/purchase-emulator/` aren't in the repo yet. Whoever picks
them up adds them in their own PR and adds the frontend job back to `.github/workflows/ci.yml`.

### First push: PR order

The code was written up front, so we're adding it in this order. Every step passes its own tests.

1. **Core & AWS** (`core/setup`): repo files (`.gitignore`, `.env.example`, `Makefile`, `README.md`,
   `CONTRIBUTING.md`, `CLAUDE.md`, `docs/`, `infra/`, `.github/`), `backend/pyproject.toml`, `uv.lock`,
   `requirements.txt`, the core files above, `tests/conftest.py`, `tests/test_store.py`.
2. **Agents** (`agents/initial`) **and Negotiation** (`negotiation/engine`). They don't depend on each
   other, so open these at the same time once step 1 is merged.
   - Agents: its files + `tests/test_pipeline.py`, `tests/test_llm.py`.
   - Negotiation: its files + `tests/test_reasoner.py`, `tests/test_negotiation.py` **without** the last
     test (`test_final_offer_asks_founder_then_accepts`), because that one needs `conversation.py`.
3. **API & conversation** (`api/conversation`), after step 2 is merged: its files + `tests/test_conversation.py`,
   `tests/test_api.py`, and add the held-back negotiation test. This is where all 49 tests pass together.

The seams between areas are small on purpose:

- Agents return a `Finding` (`models.py`). The pipeline doesn't care how it was produced.
- Everything reaches the founder through `alerts.raise_alert()` or `messaging.send_to_founder()`.
- All persistence goes through `store.py` (`get`, `list`, `put`, `update`). Entity names live in `entities.py`.
- All Claude calls go through `llm.py`, and every call has a non-LLM fallback.

## Day to day

```bash
make setup && make seed
make api            # terminal 1
make worker         # terminal 2 (only if you're touching negotiations)
make test           # before every push
make fmt            # auto-format + fix lint
```

- Branch per change: `git checkout -b <area>/<short-name>`, e.g. `agents/better-saas-prompt`.
- Keep PRs small and in your area. If you need to change a seam (`Finding`, `store.py`,
  `alerts.py`), say so in the PR and tag the affected owner.
- CI runs `ruff` and `pytest` on every PR. Don't merge red.
- New behavior gets a test. Logic that doesn't need Claude (strategy, routing, policies) should be
  tested without it. See `tests/test_reasoner.py`.
- Never commit `.env` or keys. Never hardcode credentials in the frontend: `VITE_*` values ship to the browser.

## Running with real services

| Service | What you need |
|---|---|
| Claude on Bedrock | AWS credentials (`aws configure` or `AWS_PROFILE`), model access in the Bedrock console, `RUNWAY_LLM=bedrock` |
| DynamoDB | A table (from `sam deploy`, or create `runway` with `pk`/`sk` string keys), `RUNWAY_STORE=dynamodb`, then `make seed` |
| iMessage | A Mac signed into Messages, Full Disk Access for the terminal, `make bridge`, `RUNWAY_NOTIFIER=imessage` |
| Vendor email | SES-verified sender (`RUNWAY_EMAIL_FROM`), an inbox with an app password (`RUNWAY_IMAP_*`), `RUNWAY_MAIL=live` |

Tip: for live negotiation tests, set `vendor_email` to a teammate's address and play the vendor:
`POST /negotiations {"vendor":"Cursor","price":1400,"vendor_email":"you@…","demo":false}`.
