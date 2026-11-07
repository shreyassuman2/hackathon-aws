"""Founder-set rules that let Runway act without asking.

Policy types (records in the POLICY entity):
  auto_cancel           cancel subs under $threshold_amount/mo with no seat activity in threshold_days
  auto_accept_discount  accept renewal discounts >= threshold_discount_pct on contracts < threshold_amount
  auto_approve_expense  approve an expense <= threshold_amount if this employee+merchant was approved before
  production_infra      never act autonomously on these vendors (a guard on all of the above)

Every autonomous action is written to POLICY_ACTION so it can be shown, digested and undone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from runway import entities as E
from runway.models import Finding
from runway.store import Record, find, find_one, get_store


def _policy(kind: str) -> Record | None:
    return find_one(get_store(), E.POLICY, lambda p: p.get("type") == kind and p.get("enabled", True))


def _vendor_key(name: str) -> str:
    return (name or "").strip().split(" ")[0].lower()


def same_vendor(a: str, b: str) -> bool:
    return bool(a and b) and _vendor_key(a) == _vendor_key(b)


def is_production_infra(vendor: str) -> bool:
    p = _policy("production_infra")
    if not p:
        return False
    v = vendor.lower()
    return any(i.lower() in v or v in i.lower() for i in p.get("production_infra_list") or [])


def _log(
    policy: Record, action_type: str, entity_name: str, amount: float, rationale: str, transaction_id: str | None
) -> None:
    get_store().put(
        E.POLICY_ACTION,
        {
            "policy_id": policy.get("id"),
            "transaction_id": transaction_id,
            "action_type": action_type,
            "entity_name": entity_name,
            "amount": amount,
            "rationale": rationale,
            "executed_at": datetime.now(UTC).isoformat(),
            "undo_available": True,
        },
    )


def auto_cancel(vendor: str, monthly_cost: float, transaction_id: str | None = None) -> Finding | None:
    if is_production_infra(vendor):
        return None
    p = _policy("auto_cancel")
    if not p:
        return None
    cap = float(p.get("threshold_amount") or 100)
    days = int(p.get("threshold_days") or 60)
    if monthly_cost > cap:
        return None

    seats = find(get_store(), E.SEAT, lambda s: same_vendor(s.get("tool", ""), vendor))
    if not seats:
        return None  # no usage data at all: we can't claim "zero usage", so don't act
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    if any((s.get("last_active_date") or "") >= cutoff for s in seats):
        return None

    rationale = f"{vendor} at ${monthly_cost:g}/mo: no seat activity in {days} days (rule: under ${cap:g}/mo)."
    _log(p, "auto_cancel", vendor, monthly_cost, rationale, transaction_id)
    return Finding(
        pillar="saas_sprawl",
        agent="policy.auto_cancel",
        alert_type="auto_cancel",
        autonomous=True,
        savings_monthly=monthly_cost,
        message=f"Canceled {vendor}: nobody has used it in {days} days, which matches your auto-cancel rule. "
        f"Saves ${monthly_cost:g}/mo. Reply UNDO to reverse.",
        metadata={"vendor": vendor, "rationale": rationale},
    )


def auto_accept_discount(vendor: str, current_price: float, offered_pct: float) -> bool:
    """True if a vendor's offer can be accepted without asking the founder."""
    if is_production_infra(vendor):
        return False
    p = _policy("auto_accept_discount")
    if not p:
        return False
    cap = float(p.get("threshold_amount") or 5000)
    min_pct = float(p.get("threshold_discount_pct") or 10)
    if current_price > cap or offered_pct < min_pct:
        return False
    _log(
        p,
        "auto_accept_discount",
        vendor,
        current_price,
        f"Accepted {offered_pct:g}% off {vendor} (rule: >= {min_pct:g}% on contracts under ${cap:g}/mo).",
        None,
    )
    return True


def auto_approve_expense(
    employee_id: str, merchant: str, amount: float, transaction_id: str | None = None
) -> Finding | None:
    if is_production_infra(merchant):
        return None
    p = _policy("auto_approve_expense")
    if not p:
        return None
    cap = float(p.get("threshold_amount") or 200)
    if amount > cap:
        return None
    prior = find_one(
        get_store(),
        E.TRANSACTION,
        lambda t: (
            t.get("employee_id") == employee_id
            and same_vendor(t.get("merchant", ""), merchant)
            and t.get("founder_action") == "Y"
        ),
    )
    if not prior:
        return None
    rationale = f"{merchant} ${amount:g}: same employee + merchant was approved before (under ${cap:g})."
    _log(p, "auto_approve_expense", merchant, amount, rationale, transaction_id)
    return Finding(
        pillar="compliance",
        agent="policy.auto_approve_expense",
        alert_type="auto_approve",
        autonomous=True,
        message=f"Auto-approved {merchant} ${amount:g}: matches an expense you approved before.",
        metadata={"merchant": merchant, "rationale": rationale},
    )


def update_threshold(kind: str, field: str, value: float) -> Record | None:
    p = _policy(kind)
    if not p:
        return None
    return get_store().update(E.POLICY, p["id"], {field: value})
