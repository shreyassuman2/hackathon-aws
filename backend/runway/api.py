"""HTTP API (FastAPI). Runs locally with uvicorn and on AWS Lambda via Mangum (see handlers.py).

uv run uvicorn runway.api:app --reload --port 8000
open http://localhost:8000/docs
"""

from __future__ import annotations

import hmac
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runway import alerts, conversation, digest, pipeline
from runway import entities as E
from runway.agents import ask, commands
from runway.config import get_settings
from runway.models import TransactionIn
from runway.negotiation import engine
from runway.store import Record, find, get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

settings = get_settings()


def require_token(x_runway_token: str | None = Header(default=None)) -> None:
    expected = get_settings().api_token
    if expected and not hmac.compare_digest(x_runway_token or "", expected):
        raise HTTPException(status_code=401, detail="missing or bad X-Runway-Token")


app = FastAPI(title="Runway", version="0.1.0", description="AI finance team for startups, on AWS.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = Depends(require_token)


# ── request bodies ────────────────────────────────────────────────────────────


class InboundMessage(BaseModel):
    """What the iMessage bridge posts. Field names match bridge/server.js."""

    sender: str = ""
    text: str = ""


class Question(BaseModel):
    question: str


class CommandIn(BaseModel):
    message: str


class NegotiationIn(BaseModel):
    vendor: str
    price: float
    target_pct: float | None = None
    vendor_email: str | None = None
    demo: bool | None = None


# ── helpers ───────────────────────────────────────────────────────────────────


def _employees() -> dict[str, Record]:
    return {e["id"]: e for e in get_store().list(E.EMPLOYEE)}


def _with_employee(rows: list[Record]) -> list[Record]:
    """Attach {name, role, email} like the old Supabase join did, so the frontend keeps working."""
    emps = _employees()
    out = []
    for r in rows:
        e = emps.get(r.get("employee_id") or "")
        out.append({**r, "employees": {k: e.get(k) for k in ("name", "role", "email")} if e else None})
    return out


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


# ── core ──────────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {"ok": True, "store": s.store, "llm": s.llm, "notifier": s.notifier, "mail": s.mail}


@app.post("/transactions", dependencies=[api])
async def ingest_transaction(txn: TransactionIn) -> dict[str, Any]:
    """Bank feed / purchase emulator webhook. Runs the whole pipeline and returns the alert."""
    alert = await pipeline.process(txn)
    return {"status": "processed", "alert": alert}


@app.post("/imessage/inbound", dependencies=[api])
async def imessage_inbound(msg: InboundMessage) -> dict[str, Any]:
    return await conversation.handle_inbound(msg.sender, msg.text)


@app.post("/ask", dependencies=[api])
async def ask_endpoint(q: Question) -> dict[str, str]:
    return {"question": q.question, "answer": await ask.answer(q.question)}


@app.post("/command", dependencies=[api])
async def command_endpoint(c: CommandIn) -> dict[str, str]:
    return {"reply": await commands.run(c.message)}


@app.post("/digest/{kind}", dependencies=[api])
async def send_digest(kind: Literal["morning", "weekly"]) -> dict[str, bool]:
    return {"sent": await digest.send(kind)}


# ── negotiations ──────────────────────────────────────────────────────────────


@app.get("/negotiations", dependencies=[api])
def negotiations() -> list[Record]:
    return engine.list_negotiations()


@app.post("/negotiations", dependencies=[api])
async def start_negotiation(body: NegotiationIn) -> dict[str, Any]:
    rec, created = engine.start(
        body.vendor, body.price, target_pct=body.target_pct, vendor_email=body.vendor_email, demo=body.demo
    )
    if created:
        rec = await engine.tick(rec["id"])
    return {"created": created, "negotiation": rec}


@app.post("/negotiations/{neg_id}/tick", dependencies=[api])
async def tick_negotiation(neg_id: str) -> Record:
    rec = await engine.tick(neg_id)
    if rec is None:
        raise HTTPException(404, "negotiation not found")
    return rec


@app.post("/negotiations/{neg_id}/cancel", dependencies=[api])
def cancel_negotiation(neg_id: str) -> Record:
    rec = engine.cancel(neg_id)
    if rec is None:
        raise HTTPException(404, "negotiation not found")
    return rec


# ── dashboard reads ───────────────────────────────────────────────────────────


@app.get("/transactions", dependencies=[api])
def list_transactions(limit: int = 30, pillar: str | None = None) -> list[Record]:
    rows = find(
        get_store(),
        E.TRANSACTION,
        (lambda t: t.get("pillar") == pillar) if pillar else None,
        order_by="created_at",
        desc=True,
        limit=limit,
    )
    return _with_employee(rows)


@app.get("/alerts", dependencies=[api])
def list_alerts(limit: int = 30, pending_only: bool = False) -> list[Record]:
    if pending_only:
        return alerts.pending(limit)
    return find(get_store(), E.ALERT, order_by="created_at", desc=True, limit=limit)


@app.get("/ai-usage", dependencies=[api])
def ai_usage() -> list[Record]:
    return find(get_store(), E.AI_USAGE, order_by="week_start", desc=True)


@app.get("/subscriptions", dependencies=[api])
def subscriptions() -> list[Record]:
    return find(get_store(), E.RENEWAL, order_by="renewal_date")


@app.get("/seats", dependencies=[api])
def seats() -> list[Record]:
    return _with_employee(find(get_store(), E.SEAT, order_by="last_active_date"))


@app.get("/policy-actions", dependencies=[api])
def policy_actions(limit: int = 10) -> list[Record]:
    return find(get_store(), E.POLICY_ACTION, order_by="executed_at", desc=True, limit=limit)


@app.get("/policies", dependencies=[api])
def list_policies() -> list[Record]:
    return get_store().list(E.POLICY)


@app.get("/employees", dependencies=[api])
def employees() -> list[Record]:
    return [{k: e.get(k) for k in ("id", "name", "role", "email")} for e in get_store().list(E.EMPLOYEE)]


@app.get("/dashboard/metrics", dependencies=[api])
def metrics() -> dict[str, Any]:
    store = get_store()
    since = _since(30)
    txns = find(store, E.TRANSACTION, lambda t: (t.get("created_at") or "") >= since)
    return {
        "totalMonthlySpend": round(sum(float(t.get("amount") or 0) for t in txns)),
        "identifiedSavings": round(sum(float(t.get("savings_identified") or 0) for t in store.list(E.TRANSACTION))),
        "ghostSeats": len(find(store, E.SEAT, lambda s: s.get("is_dormant"))),
        "complianceFlags": len(alerts.pending(limit=1000)),
        "activeSubscriptions": len(store.list(E.RENEWAL)),
        "activeNegotiations": len(find(store, E.NEGOTIATION, lambda n: n.get("status") in engine.ACTIVE)),
    }


@app.get("/dashboard/spend-trend", dependencies=[api])
def spend_trend(days: int = 14, bucket_days: int = 2) -> dict[str, Any]:
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    txns = find(get_store(), E.TRANSACTION, lambda t: (t.get("created_at") or "") >= start.isoformat())
    n = max(1, days // bucket_days)
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0] * n)
    for t in txns:
        idx = min(n - 1, (datetime.fromisoformat(t["created_at"]) - start).days // bucket_days)
        sums[t.get("pillar") or "unknown"][idx] += float(t.get("amount") or 0)
    ai, saas, exp = (list(map(round, sums[p])) for p in ("ai_spend", "saas_sprawl", "compliance"))
    days_out = [start + timedelta(days=i * bucket_days) for i in range(n)]
    labels = [f"{d:%b} {d.day}" for d in days_out]  # "%-d" isn't supported on Windows
    return {
        "labels": labels,
        "datasets": {
            "total": [a + s + e for a, s, e in zip(ai, saas, exp, strict=True)],
            "ai": ai,
            "saas": saas,
            "expenses": exp,
        },
    }
