# Runway: notes for AI coding agents

Read README.md and docs/ARCHITECTURE.md first.

- Backend is `backend/runway` (Python 3.12, uv). Run `make test` and `make lint` before finishing any change.
- Only `runway/llm.py` may import `anthropic`. Agents call `llm.text` / `llm.structured` / `llm.tool_chat`
  and MUST handle a `None` return with a deterministic fallback.
- Only `runway/store.py` talks to storage. Add new entity names to `entities.py`.
- Negotiation state changes go through one `store.update(..., expect_version=...)`; side effects go in the
  outbox (`_queue_email`, `_queue_text`, `_queue_record`), never inline. Keep `reasoner.decide()` pure.
- Money-moving actions need founder approval (a `Finding` with `requires_action=True`) unless a policy in
  `policies.py` allows it and logs a POLICY_ACTION.
- Tests run with no network: `RUNWAY_LLM=off`, local store, console messaging, demo mail (see tests/conftest.py).
- The frontend is slated for a redesign; keep `frontend/lib/api.js` as the only place that calls the API.
