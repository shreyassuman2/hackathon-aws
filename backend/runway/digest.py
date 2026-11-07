"""Monday brief and Friday wrap: everything the restraint filter held back, in one message."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from runway import entities as E
from runway import messaging
from runway.store import find, get_store


def _week_ago() -> str:
    return (datetime.now(UTC) - timedelta(days=7)).isoformat()


def build(kind: str = "weekly") -> tuple[str, list[str]]:
    """Returns (message text, ids of the held alerts it includes)."""
    store = get_store()
    since = _week_ago()
    txns = find(store, E.TRANSACTION, lambda t: (t.get("created_at") or "") >= since)
    actions = find(store, E.POLICY_ACTION, lambda a: (a.get("executed_at") or "") >= since)
    held = find(
        store,
        E.ALERT,
        lambda a: a.get("tier") == "informational" and not a.get("delivered") and not a.get("autonomous"),
        order_by="created_at",
        limit=10,
    )
    spend = sum(float(t.get("amount") or 0) for t in txns)
    found = sum(float(t.get("savings_identified") or 0) for t in txns)

    title = "Good morning. Your week ahead:" if kind == "morning" else "Weekly wrap:"
    lines = [title, f"${spend:,.0f} across {len(txns)} charges · ${found:,.0f}/mo in savings found."]
    if actions:
        lines.append(f"\nI acted on my own {len(actions)} time(s):")
        lines += [f"• {a['action_type'].replace('_', ' ')}: {a['entity_name']}" for a in actions[:5]]
    if held:
        lines.append("\nFYI (held so I didn't interrupt you):")
        lines += [f"• {a['message'][:90]}" for a in held]
    return "\n".join(lines), [a["id"] for a in held]


async def send(kind: str = "weekly") -> bool:
    text, ids = build(kind)
    ok = await messaging.send_to_founder(text)
    if ok:
        now = datetime.now(UTC).isoformat()
        for i in ids:
            get_store().update(E.ALERT, i, {"delivered": True, "delivered_at": now, "bundled_in_digest": True})
    return ok
