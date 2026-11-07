"""Founder commands over iMessage: "cancel Notion", "negotiate Cursor to 25%", "show pending", "undo".

`parse()` tries cheap regexes first, then (with Bedrock on) asks Claude's fast tier whether a
message is a command at all. Anything that isn't a command is a question for Ask-Anything.
`execute()` runs a parsed command and returns the reply text.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from runway import alerts, llm, policies
from runway import entities as E
from runway.persona import HELP_MENU
from runway.store import Record, find_one, get_store

Kind = Literal[
    "help",
    "pending",
    "undo",
    "cancel",
    "negotiate",
    "stop_negotiation",
    "negotiations",
    "set_auto_cancel",
    "none",
]


class Command(BaseModel):
    kind: Kind
    vendor: str | None = None
    pct: float | None = None
    amount: float | None = None


_VENDOR = r"([a-z0-9][\w .&'-]*?)"
_PATTERNS: list[tuple[str, Kind]] = [
    (r"^(?:help|\?|menu|commands|what can you do)$", "help"),
    (r"^(?:show |list |what'?s )?(?:pending|todo|to-do|open items)$", "pending"),
    (r"^undo(?: that| it| last)?$", "undo"),
    (r"^(?:stop|cancel|end) (?:the )?negotiat\w*(?: with| on| for)? " + _VENDOR + r"$", "stop_negotiation"),
    (r"^(?:stop|cancel|end) (?:the )?" + _VENDOR + r" negotiation$", "stop_negotiation"),
    (r"^(?:cancel|kill|drop) (?:our |the |my )?" + _VENDOR + r"(?: subscription| sub| plan)?$", "cancel"),
    (
        r"^negotiate (?:with |the )?"
        + _VENDOR
        + r"(?: renewal)?(?: (?:to|for|at|down) (\d{1,2}(?:\.\d+)?)\s?%(?: off)?)?$",
        "negotiate",
    ),
    (r"^(?:negotiations|deals|negotiation status|status)$", "negotiations"),
    (r"^(?:set )?auto[- ]?cancel (?:to |at |under |below )?\$?(\d+(?:\.\d+)?)(?:/mo)?$", "set_auto_cancel"),
]


def _clean(text: str) -> str:
    t = text.strip().lower().replace("’", "'")
    return re.sub(r"[.!]+$", "", t).strip()


def parse_quick(text: str) -> Command | None:
    t = _clean(text)
    for pattern, kind in _PATTERNS:
        m = re.match(pattern, t)
        if not m:
            continue
        groups = [g for g in m.groups() if g is not None]
        if kind == "set_auto_cancel":
            return Command(kind=kind, amount=float(groups[0]))
        if kind == "negotiate":
            return Command(kind=kind, vendor=groups[0].strip(), pct=float(m.group(2)) if m.group(2) else None)
        return Command(kind=kind, vendor=groups[0].strip() if groups else None)
    return None


async def parse(text: str) -> Command | None:
    """A Command, or None when the text is a question (or chit-chat) for Ask-Anything."""
    if cmd := parse_quick(text):
        return cmd
    if "?" in text:
        return None  # questions never move money; don't spend a model call on them
    out = await llm.structured(
        f"""A startup founder texted their AI finance assistant. Is this an instruction to DO one of
these things? If it is a question or anything else, kind = "none".

- cancel: cancel a SaaS subscription (vendor)
- negotiate: negotiate a vendor's renewal price (vendor, optional target pct)
- stop_negotiation: stop an ongoing negotiation (vendor)
- pending: show items waiting for approval
- undo: reverse the last automatic action
- negotiations: show negotiation status
- set_auto_cancel: change the auto-cancel threshold (amount in $/mo)
- help: what can you do

Message: {text!r}""",
        Command,
        tier="fast",
    )
    if out is None or out.kind == "none":
        return None
    if out.kind in ("cancel", "negotiate", "stop_negotiation") and not out.vendor:
        return None
    return out


# ── helpers ───────────────────────────────────────────────────────────────────


def _renewal(vendor: str) -> Record | None:
    return find_one(
        get_store(),
        E.RENEWAL,
        lambda r: policies.same_vendor(r.get("vendor", ""), vendor) and r.get("status") != "cancelled",
        order_by="renewal_date",
    )


def _title(vendor: str) -> str:
    return vendor if any(c.isupper() for c in vendor) else vendor.title()


def _date(d: str | None) -> date | None:
    try:
        return date.fromisoformat(str(d)[:10]) if d else None
    except ValueError:
        return None


def pending_lines(limit: int = 5) -> list[Record]:
    """The numbered list a founder can answer with "Y 2". Same order as `alerts.pending()`."""
    return alerts.pending(limit)


# ── command handlers ──────────────────────────────────────────────────────────


def _pending() -> str:
    rows = pending_lines()
    if not rows:
        return "Nothing is waiting on you. 🎉"
    lines = [f"{i}. {a['message'][:140]}" for i, a in enumerate(rows, 1)]
    return "Waiting on you:\n" + "\n".join(lines) + "\n\nReply Y 1 / N 1 (etc.) to answer one."


def _undo() -> str:
    store = get_store()
    act = find_one(
        store,
        E.POLICY_ACTION,
        lambda a: a.get("undo_available") and not a.get("undone"),
        order_by="executed_at",
        desc=True,
    )
    if not act:
        return "There's nothing to undo."
    store.update(E.POLICY_ACTION, act["id"], {"undone": True, "undo_available": False})
    vendor = act.get("entity_name") or "that"
    if act.get("action_type") == "auto_cancel":
        if r := find_one(store, E.RENEWAL, lambda r: policies.same_vendor(r.get("vendor", ""), vendor)):
            store.update(E.RENEWAL, r["id"], {"status": "active"})
        return f"Undone: {vendor} is back on. I won't auto-cancel it again without asking."
    return f"Undone: {act.get('action_type', 'action').replace('_', ' ')} on {vendor}."


def _cancel(vendor: str) -> str:
    from runway.negotiation import engine

    store = get_store()
    r = _renewal(vendor)
    if not r:
        return f"I don't see an active {_title(vendor)} subscription."
    name = r["vendor"]
    monthly = float(r.get("monthly_cost") or 0)
    store.update(E.RENEWAL, r["id"], {"status": "cancelled", "auto_renew": False})
    store.put(
        E.SAVINGS,
        {
            "title": f"Cancel {name}",
            "amount_monthly": monthly,
            "status": "approved",
            "source_type": "founder_command",
            "source_id": r["id"],
        },
    )
    if neg := engine.active_for(name):
        engine.cancel(neg["id"])

    msg = f"Marked {name} for cancellation: saves ${monthly:,.0f}/mo (${monthly * 12:,.0f}/yr)."
    renews, notice = _date(r.get("renewal_date")), int(r.get("notice_period_days") or 0)
    if renews:
        deadline = renews - timedelta(days=notice)
        msg += (
            f" It renews {renews:%b} {renews.day}, so it has to be cancelled in {name}'s billing settings"
            f" by {deadline:%b} {deadline.day}."
        )
    if policies.is_production_infra(name):
        msg += " Heads up: it's on your production-infra list."
    return msg


async def _negotiate(vendor: str, pct: float | None) -> str | None:
    from runway.negotiation import engine

    r = _renewal(vendor)
    if not r:
        return f"I don't have {_title(vendor)}'s contract on file, so I don't know the price to negotiate from."
    neg, created = engine.start(r["vendor"], float(r.get("monthly_cost") or 0), target_pct=pct)
    if not created:
        return f"Already negotiating with {neg['vendor']} (round {neg.get('round', 0)}, {neg['status']})."
    await engine.tick(neg["id"])  # sends the opening email and texts the founder that it went out
    return None


def _negotiations() -> str:
    from runway.negotiation import engine

    rows = engine.list_negotiations(5)
    if not rows:
        return "No negotiations yet. Try: negotiate Cursor"
    out = []
    for n in rows:
        offer = f", their offer {n['current_offer_pct']:g}%" if n.get("current_offer_pct") is not None else ""
        out.append(f"• {n['vendor']}: {n['status'].replace('_', ' ')} (round {n.get('round', 0)}{offer})")
    return "\n".join(out)


def _set_auto_cancel(amount: float) -> str:
    if policies.update_threshold("auto_cancel", "threshold_amount", amount) is None:
        return "You don't have an auto-cancel rule set up."
    return f"Done. I'll auto-cancel unused subscriptions under ${amount:g}/mo (and always tell you)."


async def execute(cmd: Command) -> str | None:
    """Run a command. Returns the reply, or None when the action already texted the founder itself."""
    match cmd.kind:
        case "help":
            return HELP_MENU
        case "pending":
            return _pending()
        case "undo":
            return _undo()
        case "cancel":
            return _cancel(cmd.vendor or "")
        case "negotiate":
            return await _negotiate(cmd.vendor or "", cmd.pct)
        case "stop_negotiation":
            from runway.negotiation import engine

            neg = engine.active_for(cmd.vendor or "")
            if not neg:
                return f"I'm not negotiating with {_title(cmd.vendor or '')} right now."
            engine.cancel(neg["id"])
            return f"Stopped the {neg['vendor']} negotiation. I won't email them again."
        case "negotiations":
            return _negotiations()
        case "set_auto_cancel":
            return _set_auto_cancel(cmd.amount or 0)
    return None


def find_pending_by_index(i: int) -> Record | None:
    rows = pending_lines()
    return rows[i - 1] if 1 <= i <= len(rows) else None
