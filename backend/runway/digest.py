"""Monday brief and Friday wrap: everything the restraint filter held back, in one text.

    morning  (Mon 8am)  held FYIs + renewals in the next 14 days + what's waiting on the founder
    weekly   (Fri 4pm)  held FYIs + savings realized this week + negotiations + autonomous actions

Held informational alerts are marked `digested` once sent, so each appears in exactly one digest.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from runway import alerts, messaging
from runway import entities as E
from runway.store import Record, find, get_store

Kind = Literal["morning", "weekly"]
MAX_ITEMS = 5


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def held_items() -> list[Record]:
    return find(
        get_store(),
        E.ALERT,
        lambda a: a.get("tier") == "informational" and not a.get("delivered") and not a.get("digested"),
        order_by="created_at",
        desc=True,
    )


def _renewals(days: int = 14) -> list[Record]:
    today = datetime.now(UTC).date()
    end = (today + timedelta(days=days)).isoformat()
    return find(
        get_store(),
        E.RENEWAL,
        lambda r: r.get("status") != "cancelled" and today.isoformat() <= (r.get("renewal_date") or "") <= end,
        order_by="renewal_date",
    )


def _short_date(d: str) -> str:
    x = date.fromisoformat(d[:10])
    return f"{x:%a %b} {x.day}"


def build(kind: Kind = "weekly") -> tuple[str, list[Record]]:
    """Returns (text, held alerts included). Pure read: nothing is marked until `send()`."""
    store = get_store()
    held = held_items()
    lines: list[str] = ["☀️ Monday brief" if kind == "morning" else "📊 Friday wrap"]

    if kind == "morning":
        if renewals := _renewals():
            lines.append("\nRenewing in the next 2 weeks:")
            lines += [
                f"• {r['vendor']} ${float(r.get('monthly_cost') or 0):,.0f}/mo, {_short_date(r['renewal_date'])}"
                for r in renewals[:MAX_ITEMS]
            ]
        if pending := alerts.pending(MAX_ITEMS):
            lines.append(f"\n{len(pending)} item(s) waiting on you. Say 'show pending'.")
    else:
        week = _since(7)
        realized = [
            s
            for s in store.list(E.SAVINGS)
            if s.get("status") in ("realized", "approved") and (s.get("created_at") or "") >= week
        ]
        if realized:
            total = sum(float(s.get("amount_monthly") or 0) for s in realized)
            lines.append(f"\nSaved this week: ${total:,.0f}/mo (${total * 12:,.0f}/yr)")
            lines += [f"• {s['title']}: ${float(s.get('amount_monthly') or 0):,.0f}/mo" for s in realized[:MAX_ITEMS]]
        negs = [n for n in store.list(E.NEGOTIATION) if (n.get("updated_at") or "") >= week]
        if negs:
            lines.append("\nNegotiations:")
            lines += [f"• {n['vendor']}: {n['status'].replace('_', ' ')}" for n in negs[:MAX_ITEMS]]
        acts = find(store, E.POLICY_ACTION, lambda a: (a.get("executed_at") or "") >= week)
        if acts:
            lines.append(f"\nI acted on my own {len(acts)} time(s) under your rules. Reply UNDO to reverse the last.")

    if held:
        lines.append("\nFYI:")
        lines += [f"• {a['message'][:160]}" for a in held[:MAX_ITEMS]]
        if len(held) > MAX_ITEMS:
            lines.append(f"…and {len(held) - MAX_ITEMS} more on the dashboard.")

    if len(lines) == 1:
        lines.append("Quiet week. Nothing needs you. 👌")
    return "\n".join(lines), held


async def send(kind: Kind = "weekly") -> dict:
    text, held = build(kind)
    ok = await messaging.send_to_founder(text)
    if ok:
        now = datetime.now(UTC).isoformat()
        for a in held:
            get_store().update(E.ALERT, a["id"], {"digested": True, "digested_at": now})
    return {"sent": ok, "kind": kind, "items": len(held), "text": text}
