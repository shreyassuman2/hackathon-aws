"""Compliance agent: scores an employee card swipe against policy.

Silent when clean, loud when off. Deterministic on purpose: policy checks should be explainable.
If a charge is flagged and we have the employee's phone, Runway asks them about it directly
(see employees.py) before bothering the founder.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from runway import entities as E
from runway.models import Finding, TransactionIn
from runway.store import find, get_store

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


def _flag_words(merchant: str) -> set[str]:
    """Whole-word match (plurals allowed) so "Alphabet" isn't a bet and "Atmosphere" isn't an ATM."""
    m = merchant.lower()
    return {flag for word, flag in RED_FLAGS.items() if re.search(rf"(?<![a-z]){re.escape(word)}s?(?![a-z])", m)}


def month_to_date(employee_id: str | None, exclude_id: str | None = None) -> float:
    """What this employee has already charged so far this calendar month."""
    if not employee_id:
        return 0.0
    start = datetime.now(UTC).strftime("%Y-%m")
    rows = find(
        get_store(),
        E.TRANSACTION,
        lambda t: (
            t.get("employee_id") == employee_id
            and t.get("id") != exclude_id
            and str(t.get("created_at") or "").startswith(start)
        ),
    )
    return sum(float(t.get("amount") or 0) for t in rows)


def check(txn: TransactionIn, employee: dict | None, month_spend: float = 0.0) -> list[str]:
    flags: list[str] = []
    cap = float((employee or {}).get("monthly_expense_cap") or 0)
    if cap and month_spend + txn.amount > cap:
        flags.append(f"over_cap:{cap:g}")
    if not (txn.memo or "").strip():
        flags.append("no_memo")
    flags.extend(sorted(_flag_words(txn.merchant)))
    return flags


def _describe(flag: str, month_total: float = 0.0) -> str:
    if flag.startswith("over_cap:"):
        cap = flag.split(":", 1)[1]
        return f"${month_total:,.0f} this month, over the ${cap} monthly cap" if month_total else f"over the ${cap} cap"
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
    month_total = month_to_date(txn.employee_id, txn.id) + txn.amount
    flags = check(txn, employee, month_total - txn.amount)
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
        message=f"Flagged: {name} spent ${txn.amount:g} at {txn.merchant} ({', '.join(_describe(f, month_total) for f in flags)}).",
        flags=flags,
        requires_action=True,
        confidence=0.9 if serious else 0.75,
        action_prompt="Approve this expense?",
        metadata={"employee": name, "employee_id": txn.employee_id, "phone": (employee or {}).get("phone")},
    )
