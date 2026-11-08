"""Inbound iMessage routing.

    sender is an employee (not the founder) ─▶ employees.handle_reply
    "y" / "n" / "y 2"                         ─▶ answer the alert just asked about (or #2 of 'show pending')
    "cancel Notion", "show pending", ...      ─▶ agents.commands
    anything else                             ─▶ Ask-Anything

Y/N is an exact-word match on the whole message ("today" is not "y", "no way that's right?" is a
question). A bare Y/N only answers the alert Runway's *last* message to the founder asked about,
while that alert is still open. After an FYI, an answer or anything else, it asks which one you mean
instead of guessing, so a stray "y" can never approve spend nobody asked about.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from runway import alerts, employees, messaging
from runway import entities as E
from runway.agents import ask, commands
from runway.store import Record, get_store

log = logging.getLogger("runway.conversation")

YES = {"y", "yes", "yep", "yeah", "yup", "ya", "ok", "okay", "sure", "approve", "approved", "do it", "go", "👍"}
NO = {"n", "no", "nope", "nah", "decline", "declined", "reject", "skip", "don't", "dont", "👎"}
_DECISION = re.compile(r"^(?P<word>[a-z'👍👎 ]+?)(?:\s*(?:to\s*)?#?\s*(?P<n>\d{1,2}))?$")


def parse_decision(text: str) -> tuple[bool, int | None] | None:
    """'y' -> (True, None); 'N 2' / 'yes to #2' -> (False/True, 2); anything else -> None."""
    t = re.sub(r"[.!]+$", "", text.strip().lower().replace("’", "'")).strip()
    m = _DECISION.match(t)
    if not m:
        return None
    word = m.group("word").strip()
    n = int(m.group("n")) if m.group("n") else None
    if word in YES:
        return True, n
    if word in NO:
        return False, n
    return None


NOTHING_ASKED = (
    "I'm not sure what that's a yes or no to: my last message didn't ask you anything. "
    "Say 'show pending', then reply Y 1 / N 1 (etc.)."
)


def asked_alert() -> Record | None:
    """The alert a bare Y/N answers: only the one Runway's last message to the founder asked about,
    and only while it's still open. Anything else (an FYI, an answer, a stale or resolved ask) is no."""
    last = messaging.last_founder_message()
    alert_id = (last or {}).get("asks_alert_id")
    if not alert_id:
        return None
    alert = get_store().get(E.ALERT, alert_id)
    if not alert or alert.get("resolved"):
        return None
    return alert


async def apply_decision(alert: Record, accept: bool) -> str | None:
    """Act on the founder's Y/N for one alert. Returns the reply text (None = the action already texted)."""
    from runway.negotiation import engine

    store = get_store()
    alerts.resolve(alert, "Y" if accept else "N")
    meta = alert.get("metadata") or {}
    kind = alert.get("alert_type")

    if kind == "negotiation_decision" and meta.get("negotiation_id"):
        await engine.founder_decision(meta["negotiation_id"], accept)
        return None  # the engine texts the outcome
    if not accept:
        return "Got it, I'll leave it." if kind != "expense_flagged" else "OK, marked as not approved."

    if kind == "negotiate_offer" and meta.get("vendor"):
        neg, created = engine.start(meta["vendor"], float(meta.get("price") or 0), alert_id=alert["id"])
        if not created:
            return f"Already negotiating with {neg['vendor']} (round {neg.get('round', 0)})."
        await engine.tick(neg["id"])  # opening email goes out; the engine texts "Sent ... our ask"
        return None
    if kind in ("expense_flagged", "categorize", "policy_violation"):
        return "Approved. ✓"
    if float(alert.get("savings_monthly") or 0) > 0:
        store.put(
            E.SAVINGS,
            {
                "title": f"{meta.get('vendor') or alert.get('pillar', '').replace('_', ' ')}: {kind}",
                "amount_monthly": float(alert["savings_monthly"]),
                "status": "approved",
                "source_type": "alert",
                "source_id": alert["id"],
            },
        )
        return f"Approved. That's ${float(alert['savings_monthly']):,.0f}/mo; I'll track it under savings."
    return "Approved. ✓"


async def _founder_reply(text: str, chat_id: str) -> str | None:
    if (d := parse_decision(text)) is not None:
        accept, n = d
        if n:  # "Y 2": explicit, from the 'show pending' list
            alert = commands.find_pending_by_index(n)
            if alert is None:
                return f"I don't have a #{n}. Say 'show pending' to see the list."
            return await apply_decision(alert, accept)
        alert = asked_alert()
        if alert is None:
            return NOTHING_ASKED
        return await apply_decision(alert, accept)

    if (cmd := await commands.parse(text)) is not None:
        return await commands.execute(cmd)

    return await ask.answer(text, chat_id)


async def handle_inbound(text: str, sender: str = "") -> dict[str, Any]:
    """Handle one inbound text. Sends the reply over the configured notifier and returns it."""
    text = (text or "").strip()
    if not text:
        return {"handled_as": "empty", "reply": None}

    # When no founder phone is configured, everyone is the founder (local dev / single-user demo).
    is_employee = bool(sender) and bool(messaging.founder_phone()) and not messaging.is_founder(sender)
    if is_employee:
        messaging.save_message(sender, "user", text)
        result = await employees.handle_reply(sender, text)
        return {"handled_as": "employee", **result, "reply": None}

    chat_id = messaging.founder_phone() or sender or "founder"
    messaging.save_message(chat_id, "user", text)
    try:
        reply = await _founder_reply(text, chat_id)
    except Exception:
        log.exception("failed to handle %r", text)
        reply = "Sorry, something went wrong on my end. Try again in a minute?"
    if reply:
        await messaging.send(chat_id if chat_id != "founder" else messaging.founder_phone(), reply)
    return {"handled_as": "founder", "reply": reply}
