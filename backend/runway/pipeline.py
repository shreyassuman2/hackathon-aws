"""Transaction pipeline: charge in → pillar → policy → specialist → alert.

record transaction ─▶ route to pillar ─▶ autonomous policy? ──yes─▶ alert (FYI)
                                           │ no
                                           ▼
                                     specialist agent ─▶ alert (restraint-filtered)
"""

from __future__ import annotations

import logging

from runway import alerts, employees, policies
from runway import entities as E
from runway.agents import ai_spend, compliance, router, saas
from runway.models import Finding, TransactionIn
from runway.store import Record, get_store

log = logging.getLogger("runway.pipeline")


def record_transaction(txn: TransactionIn) -> TransactionIn:
    """Persist the raw charge first so nothing is lost if analysis fails."""
    rec = get_store().put(E.TRANSACTION, {**txn.model_dump(exclude_none=True), "status": "received"})
    return txn.model_copy(update={"id": rec["id"]})


async def _analyze(txn: TransactionIn, pillar: str) -> Finding:
    if pillar == "ai_spend":
        return await ai_spend.analyze(txn)
    if pillar == "saas_sprawl":
        return policies.auto_cancel(txn.merchant, txn.amount, txn.id) or await saas.analyze(txn)
    if pillar == "compliance":
        if txn.employee_id and (
            auto := policies.auto_approve_expense(txn.employee_id, txn.merchant, txn.amount, txn.id)
        ):
            return auto
        return await compliance.analyze(txn)
    return Finding(
        pillar="unknown",
        agent="unclassified",
        alert_type="categorize",
        message=f"New charge: {txn.merchant}, ${txn.amount:g}. I don't recognize it.",
        requires_action=True,
        confidence=0.9,
        action_prompt="Is this an expected business expense?",
        metadata={"merchant": txn.merchant},
    )


async def process(txn: TransactionIn) -> Record:
    """Run one transaction end to end. Returns the alert that was raised."""
    store = get_store()
    if not txn.id or store.get(E.TRANSACTION, txn.id) is None:
        txn = record_transaction(txn)

    pillar, reason = await router.route(txn)
    finding = await _analyze(txn, pillar)
    store.update(
        E.TRANSACTION,
        txn.id,
        {
            "status": "analyzed",
            "pillar": finding.pillar,
            "agent_assigned": finding.agent,
            "agent_reasoning": reason,
            "savings_identified": finding.savings_monthly,
        },
    )
    alert = await alerts.raise_alert(finding, transaction_id=txn.id, amount=txn.amount)

    # Flagged expense: ask the employee first; the founder still has the alert.
    if finding.alert_type == "expense_flagged" and finding.metadata.get("phone"):
        await employees.ask_about(txn, finding, alert_id=alert["id"])
    return alert
