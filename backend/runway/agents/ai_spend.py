"""AI spend agent: spikes, wrong-model routing, forgotten batch jobs.

Looks at weekly AI_USAGE rows for the vendor, computes the week-over-week change and the
biggest model-routing saving, then has Claude phrase the alert.
"""

from __future__ import annotations

from collections import defaultdict

from runway import entities as E
from runway import llm
from runway.models import Finding, TransactionIn
from runway.persona import PERSONA
from runway.policies import same_vendor
from runway.store import Record, find, get_store

SAVINGS_ACTION_THRESHOLD = 500.0  # $/mo before we ask the founder to act
SPIKE_RATIO = 2.0  # this week >= 2x last week


def weekly_totals(rows: list[Record]) -> list[tuple[str, float]]:
    """[(week_start, total_cost)] newest first."""
    by_week: dict[str, float] = defaultdict(float)
    for r in rows:
        if r.get("week_start"):
            by_week[str(r["week_start"])] += float(r.get("total_cost") or 0)
    return sorted(by_week.items(), reverse=True)


def week_over_week(rows: list[Record]) -> float | None:
    """Ratio of the latest week to the one before (2.0 == doubled). None if not enough data."""
    weeks = weekly_totals(rows)
    if len(weeks) < 2 or weeks[1][1] <= 0:
        return None
    return weeks[0][1] / weeks[1][1]


def _template(merchant: str, amount: float, rows: list[Record], ratio: float | None) -> str:
    if not rows:
        return f"{merchant} charged ${amount:,.0f}. I don't have usage data for it yet; connect a usage export."
    latest = weekly_totals(rows)[0][0]
    driver = max((r for r in rows if str(r.get("week_start")) == latest), key=lambda r: float(r.get("total_cost") or 0))
    trend = f"up {(ratio - 1) * 100:.0f}% week over week" if ratio and ratio > 1.05 else "in line with last week"
    msg = (
        f"{merchant} bill: ${amount:,.0f}, {trend}. Biggest driver: {int(driver.get('call_count') or 0):,} "
        f"{driver.get('model')} calls for {driver.get('use_case')}."
    )
    if driver.get("recommended_model") and float(driver.get("potential_savings") or 0) > 0:
        msg += (
            f" Routing those to {driver['recommended_model']} saves about "
            f"${float(driver['potential_savings']):,.0f}/mo."
        )
    return msg


async def analyze(txn: TransactionIn) -> Finding:
    rows = find(
        get_store(),
        E.AI_USAGE,
        lambda r: same_vendor(r.get("vendor", ""), txn.merchant),
        order_by="week_start",
        desc=True,
        limit=12,
    )
    ratio = week_over_week(rows)
    spike = ratio is not None and ratio >= SPIKE_RATIO
    best = max((float(r.get("potential_savings") or 0) for r in rows), default=0.0)

    message = await llm.text(
        f"""Write a founder alert about this AI bill.

Charge: {txn.merchant}, ${txn.amount:,.2f}
Week-over-week ratio (latest/previous): {f"{ratio:.2f}" if ratio else "unknown"}
Weekly usage rows, newest first (call_count, total_cost, model, use_case, recommended_model,
potential_savings per month):
{rows}

Say whether this is a spike, which use_case and model drive the latest week, and the monthly
saving from the recommended model if there is one. End by asking whether to deploy the routing
change.""",
        system=PERSONA,
    ) or _template(txn.merchant, txn.amount, rows, ratio)

    requires_action = spike or best >= SAVINGS_ACTION_THRESHOLD
    return Finding(
        pillar="ai_spend",
        agent="ai_spend",
        alert_type="spend_spike" if spike else "ai_routing",
        message=message,
        spike_detected=spike,
        savings_monthly=best,
        requires_action=requires_action,
        action_prompt="Deploy the model-routing change?" if requires_action else None,
        metadata={"vendor": txn.merchant, "wow_ratio": ratio},
    )
