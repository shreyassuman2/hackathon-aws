"""HTTP API (FastAPI). Runs locally with `make api` and in AWS Lambda via `handlers.api_handler`.

Every route except /health requires `X-Runway-Token` when RUNWAY_API_TOKEN is set. The API can
approve spend, so always set it when the API is reachable from outside your laptop.
"""

from __future__ import annotations

import hmac
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from runway import alerts, conversation, digest, messaging, pipeline
from runway import entities as E
from runway.agents import ask
from runway.config import get_settings
from runway.models import TransactionIn
from runway.negotiation import engine
from runway.persona import BOOT_GREETING
from runway.store import Record, find, get_store


def require_token(x_runway_token: str | None = Header(default=None)) -> None:
    expected = get_settings().api_token
    if expected and not hmac.compare_digest(x_runway_token or "", expected):
        raise HTTPException(status_code=401, detail="missing or wrong X-Runway-Token")


app = FastAPI(title="Runway", version="0.1.0", description="An AI finance team for startups, in iMessage.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(dependencies=[Depends(require_token)])


def _get(entity: str, id: str) -> Record:
    rec = get_store().get(entity, id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"{entity} {id} not found")
    return rec


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "store": s.store, "llm": s.llm, "notifier": s.notifier, "mail": s.mail}


# ── transactions & alerts ─────────────────────────────────────────────────────


@api.post("/transactions")
async def create_transaction(txn: TransactionIn) -> dict:
    """A card swipe / bank-feed charge. Runs the whole pipeline and returns the alert it raised."""
    return {"alert": await pipeline.process(txn)}


@api.get("/transactions")
def list_transactions(limit: int = 50, pillar: str | None = None) -> list[Record]:
    return find(
        get_store(),
        E.TRANSACTION,
        (lambda t: t.get("pillar") == pillar) if pillar else None,
        order_by="created_at",
        desc=True,
        limit=limit,
    )


@api.get("/alerts")
def list_alerts(pending: bool = False, limit: int = 50) -> list[Record]:
    if pending:
        return alerts.pending(limit)
    return find(get_store(), E.ALERT, order_by="created_at", desc=True, limit=limit)


class Decision(BaseModel):
    accept: bool


@api.post("/alerts/{alert_id}/decision")
async def decide_alert(alert_id: str, body: Decision) -> dict:
    """The dashboard's Approve / Decline buttons. Same effect as texting Y / N."""
    alert = _get(E.ALERT, alert_id)
    if alert.get("resolved"):
        raise HTTPException(status_code=409, detail="alert already resolved")
    reply = await conversation.apply_decision(alert, body.accept)
    return {"alert": _get(E.ALERT, alert_id), "reply": reply}


# ── conversation ──────────────────────────────────────────────────────────────


class Inbound(BaseModel):
    text: str
    sender: str = ""  # phone or email from the bridge; empty = the founder


@api.post("/imessage/inbound")
async def imessage_inbound(msg: Inbound) -> dict:
    """The bridge posts every inbound iMessage here. The reply is sent via the notifier and returned."""
    return await conversation.handle_inbound(msg.text, msg.sender)


class Question(BaseModel):
    question: str = Field(min_length=1)


@api.post("/ask")
async def ask_anything(q: Question) -> dict:
    return {"answer": await ask.answer(q.question)}


@api.get("/messages")
def list_messages(chat_id: str = "", limit: int = 50) -> list[dict]:
    return messaging.chat_history(chat_id or messaging.founder_phone(), limit=limit)


@api.post("/hello")
async def hello() -> dict:
    """Send the boot greeting (handy for checking the iMessage bridge end to end)."""
    return {"sent": await messaging.send_to_founder(BOOT_GREETING)}


# ── negotiations ─────────────────────────────────────────────────────────────


class NegotiationIn(BaseModel):
    vendor: str
    price: float = Field(gt=0, description="Current monthly price")
    target_pct: float | None = Field(default=None, gt=0, lt=100)
    vendor_email: str | None = None
    demo: bool | None = None  # None = follow RUNWAY_MAIL


@api.get("/negotiations")
def list_negotiations(limit: int = 50) -> list[Record]:
    return engine.list_negotiations(limit)


@api.post("/negotiations")
async def start_negotiation(body: NegotiationIn) -> dict:
    neg, created = engine.start(
        body.vendor, body.price, target_pct=body.target_pct, vendor_email=body.vendor_email, demo=body.demo
    )
    if created:
        neg = await engine.tick(neg["id"]) or neg
    return {"negotiation": neg, "created": created}


@api.get("/negotiations/{neg_id}")
def get_negotiation(neg_id: str) -> Record:
    return _get(E.NEGOTIATION, neg_id)


@api.post("/negotiations/{neg_id}/tick")
async def tick_negotiation(neg_id: str) -> Record:
    _get(E.NEGOTIATION, neg_id)
    return await engine.tick(neg_id) or _get(E.NEGOTIATION, neg_id)


@api.post("/negotiations/{neg_id}/cancel")
def cancel_negotiation(neg_id: str) -> Record:
    _get(E.NEGOTIATION, neg_id)
    return engine.cancel(neg_id) or _get(E.NEGOTIATION, neg_id)


# ── dashboard ─────────────────────────────────────────────────────────────────


def _spend_between(start: datetime, end: datetime) -> float:
    lo, hi = start.isoformat(), end.isoformat()
    rows = find(get_store(), E.TRANSACTION, lambda t: lo <= (t.get("created_at") or "") < hi)
    return sum(float(t.get("amount") or 0) for t in rows)


@api.get("/dashboard/metrics")
async def dashboard_metrics(days: int = Query(30, ge=1, le=365)) -> dict:
    """Numbers for the dashboard's metric cards.

    totalMonthlySpend    card spend over the last `days` days
    spendChangePct       that spend vs the `days` before it, in % (None when there is nothing to compare)
    identifiedSavings    savings found so far, $/month (pending + approved + realized)
    newSavings7d         savings found in the last 7 days, $/month
    activeSubscriptions  SaaS contracts on file that aren't cancelled
    ghostSeats           seats nobody has used recently
    complianceFlags      open compliance alerts: expenses waiting on the founder
    pendingReview        compliance expenses still marked pending
    activeNegotiations   renewal negotiations in progress
    """
    store = get_store()
    spend = await ask.spend_by_pillar(days)
    savings = await ask.savings_summary()
    negs = store.list(E.NEGOTIATION)
    pending = alerts.pending(limit=1000)

    now = datetime.now(UTC)
    current = _spend_between(now - timedelta(days=days), now)
    previous = _spend_between(now - timedelta(days=2 * days), now - timedelta(days=days))
    week_ago = (now - timedelta(days=7)).isoformat()
    new_savings = sum(
        float(s.get("amount_monthly") or 0) for s in store.list(E.SAVINGS) if (s.get("created_at") or "") >= week_ago
    )
    return {
        # camelCase keys are the ones the dashboard's metric cards read (frontend/lib/api.js)
        "totalMonthlySpend": round(sum(spend["by_pillar"].values())),
        "spendChangePct": round((current - previous) / previous * 100, 1) if previous > 0 else None,
        "identifiedSavings": round(sum(savings["monthly_by_status"].values())),
        "newSavings7d": round(new_savings),
        "ghostSeats": len(find(store, E.SEAT, lambda s: s.get("is_dormant"))),
        "complianceFlags": sum(1 for a in pending if a.get("pillar") == "compliance"),
        "pendingReview": len(
            find(store, E.TRANSACTION, lambda t: t.get("pillar") == "compliance" and t.get("status") == "pending")
        ),
        "activeSubscriptions": len(find(store, E.RENEWAL, lambda r: r.get("status") != "cancelled")),
        "activeNegotiations": sum(1 for n in negs if n.get("status") in engine.ACTIVE),
        "days": days,
        "spend_total": round(sum(spend["by_pillar"].values()), 2),
        "spend_by_pillar": spend["by_pillar"],
        "savings_monthly_by_status": savings["monthly_by_status"],
        "pending_alerts": len(pending),
        "negotiations_active": sum(1 for n in negs if n.get("status") in engine.ACTIVE),
        "negotiations_won": sum(1 for n in negs if n.get("status") == "closed_won"),
        "autonomous_actions_7d": len(await ask.autonomous_actions(7)),
    }


@api.get("/dashboard/spend-trend")
def spend_trend(days: int = Query(14, ge=1, le=365), bucket_days: int = Query(2, ge=1, le=31)) -> dict:
    """Spend per pillar in `bucket_days`-day buckets over the last `days` days (the dashboard's line chart)."""
    start = datetime.now(UTC) - timedelta(days=days)
    n = max(1, days // bucket_days)
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0] * n)
    for t in find(get_store(), E.TRANSACTION, lambda t: (t.get("created_at") or "") >= start.isoformat()):
        idx = min(n - 1, (datetime.fromisoformat(t["created_at"]) - start).days // bucket_days)
        sums[t.get("pillar") or "unknown"][idx] += float(t.get("amount") or 0)
    ai, saas, exp = ([round(x) for x in sums[p]] for p in ("ai_spend", "saas_sprawl", "compliance"))
    buckets = [start + timedelta(days=i * bucket_days) for i in range(n)]
    return {
        "labels": [f"{d:%b} {d.day}" for d in buckets],  # not strftime("%-d"): that fails on Windows
        "datasets": {
            "total": [a + s + e for a, s, e in zip(ai, saas, exp, strict=True)],
            "ai": ai,
            "saas": saas,
            "expenses": exp,
        },
    }


@api.get("/subscriptions")
def list_subscriptions() -> list[Record]:
    """SaaS contracts, soonest renewal first (same data as /renewals; the dashboard uses this name)."""
    return find(get_store(), E.RENEWAL, order_by="renewal_date")


@api.get("/seats")
def list_seats() -> list[Record]:
    return find(get_store(), E.SEAT, order_by="last_active_date")


@api.get("/ai-usage")
def list_ai_usage() -> list[Record]:
    return find(get_store(), E.AI_USAGE, order_by="week_start", desc=True)


@api.get("/employees")
def list_employees() -> list[dict]:
    # Only what the dashboard shows: no phone numbers or expense caps.
    return [{k: e.get(k) for k in ("id", "name", "role", "email")} for e in get_store().list(E.EMPLOYEE)]


@api.get("/savings")
def list_savings() -> list[Record]:
    return find(get_store(), E.SAVINGS, order_by="created_at", desc=True)


@api.get("/renewals")
def list_renewals() -> list[Record]:
    return find(get_store(), E.RENEWAL, order_by="renewal_date")


@api.get("/policies")
def list_policies() -> list[Record]:
    return get_store().list(E.POLICY)


class PolicyPatch(BaseModel):
    enabled: bool | None = None
    threshold_amount: float | None = None
    threshold_days: int | None = None
    threshold_discount_pct: float | None = None


@api.patch("/policies/{policy_id}")
def update_policy(policy_id: str, patch: PolicyPatch) -> Record:
    _get(E.POLICY, policy_id)
    return get_store().update(E.POLICY, policy_id, patch.model_dump(exclude_none=True))


@api.get("/policy-actions")
def list_policy_actions(limit: int = 50) -> list[Record]:
    return find(get_store(), E.POLICY_ACTION, order_by="executed_at", desc=True, limit=limit)


class DigestIn(BaseModel):
    kind: Literal["morning", "weekly"] = "weekly"
    send: bool = True


@api.post("/digest")
async def run_digest(body: DigestIn) -> dict:
    if body.send:
        return await digest.send(body.kind)
    text, held = digest.build(body.kind)
    return {"sent": False, "kind": body.kind, "items": len(held), "text": text}


app.include_router(api)
