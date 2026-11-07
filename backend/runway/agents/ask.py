"""Ask-Anything: natural-language questions about spend, answered from the store.

With Bedrock on, Claude gets a set of read-only query tools and picks what it needs (no raw SQL,
nothing that writes). With the LLM off, a keyword matcher picks one tool and a template answers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from runway import entities as E
from runway import llm, messaging
from runway.agents import saas
from runway.agents.grounding import strip_questions
from runway.persona import PERSONA
from runway.policies import same_vendor
from runway.store import find, get_store


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _today() -> date:
    return datetime.now(UTC).date()


# ── read-only tools ───────────────────────────────────────────────────────────


async def spend_by_vendor(days: int = 30, pillar: str | None = None) -> dict[str, Any]:
    rows = find(
        get_store(),
        E.TRANSACTION,
        lambda t: (t.get("created_at") or "") >= _since(days) and (pillar is None or t.get("pillar") == pillar),
    )
    by: dict[str, float] = defaultdict(float)
    for t in rows:
        by[t["merchant"]] += float(t.get("amount") or 0)
    return {
        "days": days,
        "pillar": pillar,
        "total": round(sum(by.values()), 2),
        "by_vendor": dict(sorted(by.items(), key=lambda kv: -kv[1])[:15]),
    }


async def list_charges(min_amount: float = 0, days: int = 7, pillar: str | None = None) -> list[dict[str, Any]]:
    rows = find(
        get_store(),
        E.TRANSACTION,
        lambda t: (
            float(t.get("amount") or 0) >= min_amount
            and (t.get("created_at") or "") >= _since(days)
            and (pillar is None or t.get("pillar") == pillar)
        ),
        order_by="amount",
        desc=True,
        limit=20,
    )
    return [{k: t.get(k) for k in ("merchant", "amount", "created_at", "submitted_by", "pillar", "memo")} for t in rows]


async def dormant_seats(tool: str | None = None) -> list[dict[str, Any]]:
    emps = {e["id"]: e.get("name") for e in get_store().list(E.EMPLOYEE)}
    rows = find(
        get_store(),
        E.SEAT,
        lambda s: s.get("is_dormant") and (not tool or same_vendor(s["tool"], tool)),
        order_by="last_active_date",
    )
    return [
        {
            "tool": s["tool"],
            "employee": emps.get(s.get("employee_id"), "unassigned"),
            "last_active": s.get("last_active_date"),
        }
        for s in rows
    ]


def notice_status(renewal_date: str | None, notice_days: Any, today: date | None = None) -> dict[str, Any]:
    """The cancel-by date and whether it has already passed, so Claude doesn't do the date math."""
    try:
        renews = date.fromisoformat(str(renewal_date)[:10])
        deadline = renews - timedelta(days=int(notice_days or 0))
    except (TypeError, ValueError):
        return {}
    left = (deadline - (today or _today())).days
    return {"cancel_by": deadline.isoformat(), "days_left_to_cancel": left, "notice_window_passed": left < 0}


async def upcoming_renewals(days: int = 30) -> list[dict[str, Any]]:
    end = (_today() + timedelta(days=days)).isoformat()
    rows = find(
        get_store(),
        E.RENEWAL,
        lambda r: _today().isoformat() <= (r.get("renewal_date") or "") <= end,
        order_by="renewal_date",
    )
    return [
        {
            **{
                k: r.get(k)
                for k in (
                    "vendor",
                    "plan_tier",
                    "monthly_cost",
                    "renewal_date",
                    "auto_renew",
                    "notice_period_days",
                    "seats_paid",
                    "seats_active",
                )
            },
            **notice_status(r.get("renewal_date"), r.get("notice_period_days")),
        }
        for r in rows
    ]


async def cancel_savings(vendor: str) -> dict[str, Any]:
    rows = find(get_store(), E.RENEWAL, lambda r: same_vendor(r.get("vendor", ""), vendor))
    if not rows:
        return {"vendor": vendor, "found": False}
    r = rows[0]
    m = float(r.get("monthly_cost") or 0)
    return {
        "vendor": r["vendor"],
        "found": True,
        "monthly": m,
        "annual": m * 12,
        "renewal_date": r.get("renewal_date"),
        "notice_period_days": r.get("notice_period_days"),
    }


async def employee_spend(name: str, days: int = 90) -> dict[str, Any]:
    emps = find(get_store(), E.EMPLOYEE, lambda e: name.lower() in (e.get("name") or "").lower())
    if not emps:
        return {"employee": name, "found": False}
    ids = {e["id"] for e in emps}
    rows = find(
        get_store(),
        E.TRANSACTION,
        lambda t: t.get("employee_id") in ids and (t.get("created_at") or "") >= _since(days),
        order_by="amount",
        desc=True,
    )
    return {
        "employee": emps[0]["name"],
        "found": True,
        "days": days,
        "total": round(sum(float(t.get("amount") or 0) for t in rows), 2),
        "charges": [
            {"merchant": t["merchant"], "amount": t["amount"], "date": t["created_at"][:10]} for t in rows[:10]
        ],
    }


async def autonomous_actions(days: int = 7) -> list[dict[str, Any]]:
    rows = find(
        get_store(),
        E.POLICY_ACTION,
        lambda a: (a.get("executed_at") or "") >= _since(days),
        order_by="executed_at",
        desc=True,
        limit=20,
    )
    return [{k: a.get(k) for k in ("action_type", "entity_name", "amount", "rationale", "executed_at")} for a in rows]


async def savings_summary() -> dict[str, Any]:
    rows = get_store().list(E.SAVINGS)
    by: dict[str, float] = defaultdict(float)
    for r in rows:
        by[r.get("status") or "pending"] += float(r.get("amount_monthly") or 0)
    return {
        "monthly_by_status": dict(by),
        "items": [
            {"title": r["title"], "monthly": r.get("amount_monthly"), "status": r.get("status")} for r in rows[:15]
        ],
    }


async def negotiations() -> list[dict[str, Any]]:
    from runway.negotiation.engine import list_negotiations

    return [
        {k: n.get(k) for k in ("vendor", "status", "round", "target_pct", "current_offer_pct", "outcome_notes")}
        for n in list_negotiations(10)
    ]


async def vendor_opportunities(vendor: str) -> dict[str, Any]:
    """Every savings signal for one SaaS vendor, biggest first."""
    sig = saas.gather(vendor)
    opps = saas.opportunities(vendor, sig)
    return {
        "vendor": vendor,
        "renewal": sig.renewal and {k: sig.renewal.get(k) for k in ("renewal_date", "monthly_cost", "plan_tier")},
        "opportunities": [{"kind": o.kind, "monthly": o.savings_monthly, "summary": o.summary} for o in opps],
        "note": "Savings can overlap. Quote each one separately; do not add them up or claim a total.",
    }


async def spend_by_pillar(days: int = 30) -> dict[str, Any]:
    rows = find(get_store(), E.TRANSACTION, lambda t: (t.get("created_at") or "") >= _since(days))
    by: dict[str, float] = defaultdict(float)
    vendors: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in rows:
        pillar = t.get("pillar") or "unclassified"
        amount = float(t.get("amount") or 0)
        by[pillar] += amount
        vendors[pillar][t["merchant"]] += amount
    return {
        "days": days,
        "by_pillar": {k: round(v, 2) for k, v in sorted(by.items(), key=lambda kv: -kv[1])},
        "top_vendors": {
            p: {m: round(v, 2) for m, v in sorted(vs.items(), key=lambda kv: -kv[1])[:3]} for p, vs in vendors.items()
        },
    }


def _tool(fn, description: str, props: dict[str, Any], required: list[str] | None = None) -> llm.Tool:
    return llm.Tool(
        fn.__name__,
        description,
        {"type": "object", "properties": props, "required": required or [], "additionalProperties": False},
        fn,
    )


_DAYS = {"type": "integer", "description": "Look-back window in days"}
_PILLAR = {"type": "string", "enum": ["ai_spend", "saas_sprawl", "compliance", "unknown"]}
TOOLS = [
    _tool(
        spend_by_vendor,
        "Total spend grouped by vendor over a window, optionally for one pillar.",
        {"days": _DAYS, "pillar": _PILLAR},
    ),
    _tool(
        list_charges,
        "Individual charges at or above an amount over a window, biggest first.",
        {"min_amount": {"type": "number"}, "days": _DAYS, "pillar": _PILLAR},
    ),
    _tool(
        dormant_seats, "Seats nobody is using, optionally for one tool (e.g. 'Linear').", {"tool": {"type": "string"}}
    ),
    _tool(upcoming_renewals, "Subscriptions renewing within N days.", {"days": _DAYS}),
    _tool(cancel_savings, "What cancelling a vendor would save.", {"vendor": {"type": "string"}}, ["vendor"]),
    _tool(
        employee_spend,
        "One employee's card spend over a window.",
        {"name": {"type": "string"}, "days": _DAYS},
        ["name"],
    ),
    _tool(
        vendor_opportunities,
        "Savings opportunities for one SaaS vendor: dormant seats, downgrades, overlaps, unused add-ons.",
        {"vendor": {"type": "string"}},
        ["vendor"],
    ),
    _tool(
        spend_by_pillar,
        "Total spend split by pillar (AI, SaaS, compliance) over a window, with the top three vendors in each.",
        {"days": _DAYS},
    ),
    _tool(autonomous_actions, "Actions Runway took on its own under the founder's policies.", {"days": _DAYS}),
    _tool(savings_summary, "Savings identified and realized so far.", {}),
    _tool(negotiations, "Status of renewal negotiations Runway is running.", {}),
]


# ── no-LLM fallback ───────────────────────────────────────────────────────────


async def _fallback(q: str) -> str:
    low = q.lower()
    if "renew" in low:
        rows = await upcoming_renewals(30)
        if not rows:
            return "Nothing renews in the next 30 days."
        return "Renewing in the next 30 days:\n" + "\n".join(
            f"• {r['vendor']}: ${float(r['monthly_cost'] or 0):,.0f}/mo on {r['renewal_date']}" for r in rows
        )
    if any(w in low for w in ("dormant", "not using", "unused", "inactive", "seat")):
        tool = next((t for t in ("linear", "cursor", "figma", "notion", "slack", "github", "zoom") if t in low), None)
        rows = await dormant_seats(tool)
        if not rows:
            return "No dormant seats found."
        return f"{len(rows)} dormant seat(s):\n" + "\n".join(f"• {r['tool']}: {r['employee']}" for r in rows[:10])
    if "save" in low or "saving" in low:
        s = await savings_summary()
        return "Savings so far (monthly): " + ", ".join(f"{k} ${v:,.0f}" for k, v in s["monthly_by_status"].items())
    if "negotiat" in low:
        rows = await negotiations()
        return "\n".join(f"• {n['vendor']}: {n['status']} (round {n['round']})" for n in rows) or "No negotiations yet."
    if " ai" in f" {low}" or "anthropic" in low or "openai" in low:
        s = await spend_by_vendor(30, "ai_spend")
        return f"AI spend, last 30 days: ${s['total']:,.0f}. " + ", ".join(
            f"{k} ${v:,.0f}" for k, v in s["by_vendor"].items()
        )
    s = await spend_by_vendor(30)
    top = ", ".join(f"{k} ${v:,.0f}" for k, v in list(s["by_vendor"].items())[:5])
    return f"Last 30 days: ${s['total']:,.0f} total. Top vendors: {top}."


async def answer(question: str, chat_id: str = "") -> str:
    history = messaging.chat_history(chat_id, limit=8) if chat_id else []
    # History ends with the question itself when it came in over iMessage; don't send it twice.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == question:
        history = history[:-1]
    while history and history[0]["role"] != "user":
        history = history[1:]
    reply = await llm.tool_chat(
        [*history, {"role": "user", "content": question}],
        TOOLS,
        system=PERSONA
        + f"\n\nToday is {_today().isoformat()}. Answer from the tools only. Only state reasons that appear in the "
        "tool results. For spend questions name the top three vendors with dollar amounts and say the window (the tools use "
        "days, so say 'last 30 days', not 'last month'). Never add savings together or claim a total saving. Do not add commentary that is not in the tool results. Never end with a question or an offer: a bare 'yes' from the founder approves the pending alert.",
    )
    # Belt and braces: a reply like "Want me to...?" would make the founder's "y" approve a pending alert.
    return (strip_questions(reply) if reply else None) or await _fallback(question)
