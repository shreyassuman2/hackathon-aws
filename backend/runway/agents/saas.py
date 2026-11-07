"""SaaS agent: ghost seats, tier downgrades, overlapping tools, unused add-ons, shadow IT, renewals.

Collects every signal for the vendor, ranks the opportunities by monthly saving, and leads with
the biggest. If a renewal is coming up, approving the alert launches a negotiation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from runway import entities as E
from runway import llm
from runway.models import Finding, TransactionIn
from runway.persona import PERSONA
from runway.policies import same_vendor
from runway.store import Record, find, get_store

NEGOTIATE_WINDOW_DAYS = 45


@dataclass(frozen=True)
class Opportunity:
    kind: str
    savings_monthly: float
    summary: str


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Signals:
    seats: list[Record]
    renewal: Record | None
    overlaps: list[Record]
    waste: list[Record]
    tiers: list[Record]
    shadow: list[Record]

    def as_prompt(self) -> str:
        return (
            f"Seats: {self.seats}\nRenewal: {self.renewal}\nTool overlaps: {self.overlaps}\n"
            f"Unused features: {self.waste}\nTier downgrades: {self.tiers}\nShadow IT: {self.shadow}"
        )


def gather(vendor: str) -> Signals:
    s = get_store()
    match = lambda key: lambda r: same_vendor(r.get(key, ""), vendor)  # noqa: E731
    renewals = find(s, E.RENEWAL, match("vendor"), order_by="renewal_date")
    return Signals(
        seats=find(s, E.SEAT, match("tool")),
        renewal=renewals[0] if renewals else None,
        overlaps=find(s, E.OVERLAP, lambda r: any(same_vendor(t, vendor) for t in r.get("tools") or [])),
        waste=find(s, E.FEATURE_WASTE, match("vendor")),
        tiers=find(s, E.PLAN_OPT, match("vendor")),
        shadow=find(s, E.SHADOW_IT, match("vendor")),
    )


def opportunities(vendor: str, sig: Signals) -> list[Opportunity]:
    out: list[Opportunity] = []
    if sig.seats:
        dormant = sum(1 for x in sig.seats if x.get("is_dormant"))
        if dormant:
            monthly = _f(sig.renewal.get("monthly_cost")) if sig.renewal else 0.0
            save = monthly * dormant / len(sig.seats)
            out.append(
                Opportunity(
                    "ghost_seats",
                    save,
                    f"{dormant} of {len(sig.seats)} {vendor} seats are dormant"
                    + (f" (~${save:,.0f}/mo)" if save else ""),
                )
            )
    for t in sig.tiers:
        if (save := _f(t.get("monthly_savings"))) > 0:
            out.append(
                Opportunity(
                    "downgrade",
                    save,
                    f"downgrade {t.get('current_plan')} → "
                    f"{t.get('recommended_plan')} saves ${save:,.0f}/mo ({t.get('reason')})",
                )
            )
    for o in sig.overlaps:
        if (save := _f(o.get("estimated_savings"))) > 0:
            out.append(
                Opportunity(
                    "overlap",
                    save,
                    f"{', '.join(o.get('tools') or [])} overlap: "
                    f"{o.get('recommended_consolidation')} (~${save:,.0f}/mo)",
                )
            )
    for w in sig.waste:
        if (cost := _f(w.get("monthly_cost"))) > 0:
            out.append(
                Opportunity(
                    "feature_waste",
                    cost,
                    f"'{w.get('feature')}' costs ${cost:,.0f}/mo and is barely used. {w.get('recommendation')}",
                )
            )
    for x in sig.shadow:
        out.append(
            Opportunity(
                "shadow_it",
                _f(x.get("monthly_cost")),
                f"unapproved {vendor} spend ~${_f(x.get('monthly_cost')):,.0f}/mo (risk: {x.get('risk_level')})",
            )
        )
    return sorted(out, key=lambda o: o.savings_monthly, reverse=True)


def days_until(d: str | None, today: date | None = None) -> int | None:
    if not d:
        return None
    try:
        return (date.fromisoformat(str(d)[:10]) - (today or datetime.now(UTC).date())).days
    except ValueError:
        return None


def _template(txn: TransactionIn, sig: Signals, opps: list[Opportunity], days: int | None) -> str:
    parts = [f"{txn.merchant} charged ${txn.amount:,.0f}."]
    if sig.renewal:
        when = f"in {days} days" if days is not None and days >= 0 else f"on {sig.renewal.get('renewal_date')}"
        parts.append(
            f"{sig.renewal.get('plan_tier', '')} plan at ${_f(sig.renewal.get('monthly_cost')):,.0f}/mo "
            f"renews {when}.".strip()
        )
    parts.append(f"Biggest lever: {opps[0].summary}." if opps else "No waste signals yet.")
    return " ".join(parts)


async def analyze(txn: TransactionIn) -> Finding:
    sig = gather(txn.merchant)
    opps = opportunities(txn.merchant, sig)
    days = days_until(sig.renewal.get("renewal_date")) if sig.renewal else None
    negotiable = sig.renewal is not None and days is not None and 0 <= days <= NEGOTIATE_WINDOW_DAYS
    monthly = _f(sig.renewal.get("monthly_cost")) if sig.renewal else txn.amount

    ask = (
        f"Want me to negotiate the {txn.merchant} renewal?"
        if negotiable
        else "Want me to act on this?"
        if opps
        else None
    )
    message = await llm.text(
        f"""SaaS charge: {txn.merchant}, ${txn.amount:,.2f}. Days until renewal: {days}.
Everything we know about this vendor:
{sig.as_prompt()}

Ranked opportunities (biggest first): {[o.summary for o in opps]}

Write the founder alert. Lead with the biggest saving. Mention seat counts and the renewal date
if present. Don't ask a question; the approval prompt is added separately.""",
        system=PERSONA,
    ) or _template(txn, sig, opps, days)

    return Finding(
        pillar="saas_sprawl",
        agent="saas",
        alert_type="negotiate_offer" if negotiable else (opps[0].kind if opps else "saas_review"),
        message=message,
        requires_action=ask is not None,
        action_prompt=ask,
        confidence=0.9 if opps or negotiable else 0.5,
        savings_monthly=opps[0].savings_monthly if opps else 0.0,
        days_until_renewal=days,
        metadata={
            "vendor": txn.merchant,
            "price": monthly,
            "opportunity": opps[0].kind if opps else None,
            "seats_paid": len(sig.seats),
            "seats_dormant": sum(1 for x in sig.seats if x.get("is_dormant")),
        },
    )
