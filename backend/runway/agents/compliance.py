"""Compliance agent: scores an employee card swipe against policy.

Silent when clean, loud when off. Deterministic on purpose: policy checks should be explainable.
If a charge is flagged and we have the employee's phone, Runway asks them about it directly
(see employees.py) before bothering the founder.
"""

from __future__ import annotations

from runway import entities as E
from runway.models import Finding, TransactionIn
from runway.store import get_store

RED_FLAGS = {
    "casino": "gambling",
    "bet": "gambling",
    "poker": "gambling",
    "strip club": "adult",
    "gentlemen": "adult",
    "cash advance": "cash_advance",
    "atm": "cash_advance",
    "liquor": "alcohol",
}


def check(txn: TransactionIn, employee: dict | None) -> list[str]:
    flags: list[str] = []
    cap = float((employee or {}).get("monthly_expense_cap") or 0)
    if cap and txn.amount > cap:
        flags.append(f"over_cap:{cap:g}")
    if not (txn.memo or "").strip():
        flags.append("no_memo")
    m = txn.merchant.lower()
    flags.extend(sorted({flag for word, flag in RED_FLAGS.items() if word in m}))
    return flags


def _describe(flag: str) -> str:
    if flag.startswith("over_cap:"):
        return f"over the ${flag.split(':', 1)[1]} cap"
    return {
        "no_memo": "no memo",
        "gambling": "looks like gambling",
        "adult": "adult venue",
        "cash_advance": "cash advance",
        "alcohol": "liquor store",
    }.get(flag, flag)


async def analyze(txn: TransactionIn) -> Finding:
    employee = get_store().get(E.EMPLOYEE, txn.employee_id) if txn.employee_id else None
    name = (employee or {}).get("name") or txn.submitted_by or "Unknown"
    flags = check(txn, employee)
    if not flags:
        return Finding(
            pillar="compliance",
            agent="compliance",
            alert_type="expense_ok",
            message=f"✓ Auto-approved: {name}, ${txn.amount:g} at {txn.merchant}.",
            metadata={"employee": name, "employee_id": txn.employee_id},
        )
    serious = any(f in {"gambling", "adult", "cash_advance"} for f in flags)
    return Finding(
        pillar="compliance",
        agent="compliance",
        alert_type="expense_flagged",
        message=f"Flagged: {name} spent ${txn.amount:g} at {txn.merchant} ({', '.join(map(_describe, flags))}).",
        flags=flags,
        requires_action=True,
        confidence=0.9 if serious else 0.75,
        action_prompt="Approve this expense?",
        metadata={"employee": name, "employee_id": txn.employee_id, "phone": (employee or {}).get("phone")},
    )
