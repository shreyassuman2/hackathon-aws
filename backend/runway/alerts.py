"""Alerts: the record of everything Runway found, and whether the founder was told.

`raise_alert()` is the single funnel: Finding -> ALERT row -> restraint decision -> maybe a text.
Held alerts are delivered later by `flush_held()` (decision_needed, once business hours start)
or bundled into the digest (informational).
"""

from __future__ import annotations

from datetime import UTC, datetime

from runway import entities as E
from runway import messaging, restraint
from runway.models import Finding
from runway.store import Record, find, get_store


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def raise_alert(f: Finding, *, transaction_id: str | None = None, amount: float = 0.0) -> Record:
    store = get_store()
    if f.autonomous:
        # The policy already acted. Tell the founder right away so nothing feels hidden.
        tier, reason, send_now = "informational", "autonomous policy action (always reported)", True
    else:
        tier, reason = restraint.classify(f, amount)
        send_now = restraint.should_send_now(tier)

    alert = store.put(
        E.ALERT,
        {
            "transaction_id": transaction_id,
            "pillar": f.pillar,
            "agent": f.agent,
            "alert_type": f.alert_type,
            "message": f.message,
            "requires_action": f.requires_action,
            "action_prompt": f.action_prompt,
            "autonomous": f.autonomous,
            "savings_monthly": f.savings_monthly,
            "metadata": f.metadata,
            "tier": tier,
            "tier_reason": reason,
            "resolved": not f.requires_action,
            "delivered": False,
        },
    )
    if send_now:
        alert = await deliver(alert)
    return alert


async def deliver(alert: Record) -> Record:
    ask = alert.get("action_prompt") if alert.get("requires_action") else None
    if await messaging.send_to_founder(alert["message"], ask=ask, alert_id=alert["id"]):
        return get_store().update(E.ALERT, alert["id"], {"delivered": True, "delivered_at": _now()})
    return alert


async def flush_held(now: datetime | None = None) -> int:
    """Send held decision_needed alerts once it's business hours. Call this on a schedule."""
    if not restraint.should_send_now("decision_needed", now):
        return 0
    held = find(
        get_store(),
        E.ALERT,
        lambda a: a.get("tier") == "decision_needed" and not a.get("delivered") and not a.get("resolved"),
        order_by="created_at",
    )
    for a in held:
        await deliver(a)
    return len(held)


def pending(limit: int = 5) -> list[Record]:
    return find(
        get_store(),
        E.ALERT,
        lambda a: a.get("requires_action") and not a.get("resolved"),
        order_by="created_at",
        desc=True,
        limit=limit,
    )


def resolve(alert: Record, choice: str) -> Record:
    store = get_store()
    updated = store.update(E.ALERT, alert["id"], {"resolved": True, "founder_action": choice, "resolved_at": _now()})
    if alert.get("transaction_id"):
        try:
            store.update(E.TRANSACTION, alert["transaction_id"], {"founder_action": choice})
        except KeyError:
            pass
    return updated
