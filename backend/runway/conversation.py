"""Inbound iMessage handling: who sent it, what kind of message it is, what to do.

employee? ──▶ employees.handle_reply
menu word ──▶ help text
Y / N     ──▶ resolve the latest pending alert and carry out the approved action
command   ──▶ agents.commands
anything else ──▶ agents.ask (natural-language Q&A)
"""

from __future__ import annotations

import re

from runway import alerts, employees, messaging
from runway import entities as E
from runway.agents import ask, commands
from runway.negotiation import engine
from runway.persona import HELP_MENU
from runway.store import get_store

YES = {
    "y",
    "yes",
    "yep",
    "yeah",
    "yup",
    "ok",
    "okay",
    "sure",
    "approve",
    "approved",
    "confirm",
    "go",
    "do it",
    "send it",
    "go ahead",
    "sounds good",
    "proceed",
    "deploy",
    "👍",
}
NO = {
    "n",
    "no",
    "nope",
    "nah",
    "skip",
    "pass",
    "reject",
    "don't",
    "dont",
    "hold off",
    "not now",
    "cancel that",
    "actually no",
    "👎",
}
MENU = {"hi", "hello", "hey", "help", "menu", "start", "runway", "?", "commands"}


def yes_or_no(text: str) -> bool | None:
    """Whole-message match only, so 'no, skip it today' is a no and 'yesterday's bill?' is a question."""
    t = re.sub(r"[.!,]+$", "", text.strip().lower())
    t = re.sub(r"\s+", " ", t)
    first = re.split(r"[ ,]", t)[0]
    if t in YES or (first in YES and len(t.split()) <= 3):
        return True
    if t in NO or (first in NO and len(t.split()) <= 4):
        return False
    return None


async def _execute(alert: dict) -> str:
    """Carry out an approved alert. Returns the confirmation text."""
    kind = alert.get("alert_type")
    meta = alert.get("metadata") or {}
    vendor = meta.get("vendor") or "the vendor"

    if kind == "negotiate_offer":
        if not meta.get("price"):
            return f"I need {vendor}'s current price before I can negotiate."
        neg, created = engine.start(
            vendor, float(meta["price"]), target_pct=meta.get("target_pct"), alert_id=alert["id"]
        )
        if not created:
            return f"Already negotiating with {vendor} (round {neg['round']})."
        await engine.tick(neg["id"])  # sends round 1 right away; the worker takes it from here
        return ""
    if kind == "negotiation_decision" and meta.get("negotiation_id"):
        await engine.founder_decision(meta["negotiation_id"], accept=True)
        return ""
    if kind == "cancel_requested":
        get_store().put(
            E.SAVINGS,
            {
                "title": f"Cancel {vendor}",
                "amount_monthly": meta.get("price") or 0,
                "status": "pending",
                "source_type": "alert",
                "source_id": alert["id"],
            },
        )
        return f"✅ Cancellation request sent to {vendor}. I'll confirm when they process it."
    if kind == "downgrade_requested":
        return f"✅ Downgrade request sent to {vendor}."
    if kind == "expense_flagged":
        return f"✅ Approved {meta.get('employee', 'the')} expense."
    if kind == "ai_routing" or kind == "spend_spike":
        return "✅ Routing change queued. Here's what changes: cheap, high-volume calls move to the smaller model."
    return "✅ Done."


async def _decline(alert: dict) -> str:
    meta = alert.get("metadata") or {}
    if alert.get("alert_type") == "negotiation_decision" and meta.get("negotiation_id"):
        await engine.founder_decision(meta["negotiation_id"], accept=False)
        return ""
    return "Skipped. Say the word if you change your mind."


def undo_last_action() -> str:
    """Mark the most recent autonomous action as undone. (Reversing it at the vendor is still manual.)"""
    from datetime import UTC, datetime

    from runway.store import find_one

    act = find_one(
        get_store(),
        E.POLICY_ACTION,
        lambda a: a.get("undo_available") and not a.get("undone_at"),
        order_by="executed_at",
        desc=True,
    )
    if not act:
        return "There's no automatic action to undo."
    get_store().update(
        E.POLICY_ACTION, act["id"], {"undone_at": datetime.now(UTC).isoformat(), "undo_available": False}
    )
    return f"Undone: {act['action_type'].replace('_', ' ')} for {act['entity_name']}. I've logged it for follow-up."


async def handle_yes_no(yes: bool) -> str:
    alert = alerts.latest_pending()
    if not alert:
        return "Nothing is waiting on you right now."
    alerts.resolve(alert, "Y" if yes else "N")
    return await (_execute(alert) if yes else _decline(alert))


async def handle_inbound(sender: str, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"status": "ignored"}
    messaging.save_message(sender, "user", text)

    if sender and not messaging.is_founder(sender) and messaging.founder_phone():
        return await employees.handle_reply(sender, text)

    if text.lower().strip("!. ") in MENU:
        await messaging.send_to_founder(HELP_MENU)
        return {"status": "menu"}

    yn = yes_or_no(text)
    if yn is not None:
        reply = await handle_yes_no(yn)
        kind = "yes_no"
    elif text.upper() == "UNDO":
        reply = undo_last_action()
        kind = "undo"
    elif commands.looks_like_command(text):
        reply = await commands.run(text)
        kind = "command"
    else:
        reply = await ask.answer(text, chat_id=sender)
        kind = "question"

    if reply:
        await messaging.send_to_founder(reply)
    return {"status": kind, "reply": reply}
