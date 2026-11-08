"""Employee side-threads: when an expense is flagged, Runway texts the employee directly.

The founder only hears about it again if the employee's answer is a red flag.
"""

from __future__ import annotations

from runway import entities as E
from runway import messaging
from runway.models import TransactionIn
from runway.store import Record, find, find_one, get_store

ESCALATE_WORDS = ("don't know", "dont know", "not mine", "wasn't me", "wasnt me", "fraud", "stolen", "no idea")


async def ask_about(txn: TransactionIn, finding, *, alert_id: str | None = None) -> Record:
    question = (
        f"Hi {finding.metadata.get('employee', '').split(' ')[0] or 'there'}, it's Runway. I saw a "
        f"${txn.amount:g} charge at {txn.merchant} on your card. What was it for? (one line is fine)"
    )
    thread = get_store().put(
        E.EMPLOYEE_THREAD,
        {
            "employee_id": txn.employee_id,
            "transaction_id": txn.id,
            "alert_id": alert_id,
            "state": "awaiting_reply",
            "question": question,
        },
    )
    await messaging.send(finding.metadata["phone"], question)
    return thread


def employee_by_phone(phone: str) -> Record | None:
    p = messaging.normalize_phone(phone)
    return find_one(get_store(), E.EMPLOYEE, lambda e: messaging.normalize_phone(e.get("phone")) == p)


async def handle_reply(phone: str, text: str) -> dict:
    store = get_store()
    emp = employee_by_phone(phone)
    if not emp:
        return {"status": "unknown_sender"}
    threads = find(
        store,
        E.EMPLOYEE_THREAD,
        lambda t: t.get("employee_id") == emp["id"] and t.get("state") == "awaiting_reply",
        order_by="created_at",
        desc=True,
        limit=1,
    )
    if not threads:
        return {"status": "no_open_thread", "employee": emp["name"]}
    thread = threads[0]
    # iMessage smart punctuation turns don't into don’t.
    normalized = text.lower().replace("\u2019", "'")
    escalate = any(w in normalized for w in ESCALATE_WORDS)
    store.update(
        E.EMPLOYEE_THREAD,
        thread["id"],
        {
            "state": "escalated" if escalate else "resolved",
            "employee_response": text,
        },
    )
    await messaging.send(
        phone,
        "Thanks, got it." if not escalate else "Thanks for flagging. I've let the founder know and we'll look into it.",
    )
    if escalate:
        await messaging.send_to_founder(
            f'🚨 {emp["name"]} says a charge on their card isn\'t theirs: "{text}". You may want to freeze the card.'
        )
    elif thread.get("alert_id"):
        await messaging.send_to_founder(
            f'{emp["name"]} explained the flagged charge: "{text}"', ask="Approve it?", alert_id=thread["alert_id"]
        )
    return {"status": "escalated" if escalate else "resolved", "employee": emp["name"]}
