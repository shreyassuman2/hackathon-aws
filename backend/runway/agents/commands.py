"""Founder commands: "cancel Notion", "negotiate Cursor", "set auto-cancel to $50", "show pending".

Commands that change money (cancel, negotiate, downgrade) never execute directly: they create a
pending alert and the founder confirms with Y. That's the one-tap-approval rule.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from runway import alerts, llm
from runway import entities as E
from runway.config import get_settings
from runway.models import Finding
from runway.negotiation import engine
from runway.policies import same_vendor, update_threshold
from runway.store import find, get_store

CommandName = Literal[
    "cancel",
    "negotiate",
    "downgrade",
    "approve",
    "reject",
    "update_policy",
    "show_pending",
    "stop_negotiation",
    "unknown",
]

COMMAND_PREFIX = re.compile(
    r"^\s*(cancel|negotiate|downgrade|approve|reject|set|change|update|show pending|"
    r"pending|stop negotiat)",
    re.I,
)


class Command(BaseModel):
    command: CommandName
    vendor: str | None = None
    seats: int | None = None
    policy: Literal["auto_cancel", "auto_accept_discount", "auto_approve_expense"] | None = None
    value: float | None = None
    unit: Literal["dollars", "days", "percent"] | None = None


def looks_like_command(text: str) -> bool:
    return bool(COMMAND_PREFIX.match(text))


def parse_fallback(text: str) -> Command:
    low = text.strip().lower()
    m = re.match(
        r"^(cancel|negotiate|downgrade)\s+(?:the\s+|with\s+|our\s+)?(.+?)(?:\s+renewal|\s+to\s+(\d+).*)?$", low
    )
    if m:
        return Command(
            command=m.group(1), vendor=m.group(2).strip().title(), seats=int(m.group(3)) if m.group(3) else None
        )
    if low.startswith(("show pending", "pending")):
        return Command(command="show_pending")
    if low.startswith("approve"):
        return Command(command="approve")
    if low.startswith("reject"):
        return Command(command="reject")
    if low.startswith("stop negotiat"):
        vendor = low.split(" ", 2)[2].title() if len(low.split(" ")) > 2 else None
        return Command(command="stop_negotiation", vendor=vendor)
    m = re.search(
        r"(auto[- ]?cancel|auto[- ]?accept|discount|auto[- ]?approve|expense).*?(\d+(?:\.\d+)?)\s*(%|days?)?", low
    )
    if m:
        policy = (
            "auto_cancel"
            if "cancel" in m.group(1)
            else "auto_accept_discount"
            if "accept" in m.group(1) or "discount" in m.group(1)
            else "auto_approve_expense"
        )
        unit = "percent" if m.group(3) == "%" else "days" if m.group(3) else "dollars"
        return Command(command="update_policy", policy=policy, value=float(m.group(2)), unit=unit)
    return Command(command="unknown")


async def parse(text: str) -> Command:
    out = await llm.structured(
        f"""Parse this founder text message into a command.

Message: {text}

Commands: cancel <vendor>, negotiate <vendor> (renewal discount), downgrade <vendor> [to N seats],
approve / reject (the latest pending item), show_pending, stop_negotiation <vendor>,
update_policy (policy: auto_cancel | auto_accept_discount | auto_approve_expense; value + unit),
unknown (not a command).""",
        Command,
        tier="fast",
    )
    return out or parse_fallback(text)


def _renewal(vendor: str):
    rows = find(get_store(), E.RENEWAL, lambda r: same_vendor(r.get("vendor", ""), vendor), order_by="renewal_date")
    return rows[0] if rows else None


async def run(text: str) -> str:
    cmd = await parse(text)
    s = get_settings()

    if cmd.command in ("cancel", "negotiate", "downgrade") and not cmd.vendor:
        return f"Which vendor should I {cmd.command}?"

    if cmd.command == "cancel":
        r = _renewal(cmd.vendor)
        cost = float(r.get("monthly_cost") or 0) if r else 0.0
        vendor = r["vendor"] if r else cmd.vendor
        detail = f" (${cost:,.0f}/mo, renews {r.get('renewal_date')})" if r else ""
        await alerts.raise_alert(
            Finding(
                pillar="saas_sprawl",
                agent="command",
                alert_type="cancel_requested",
                requires_action=True,
                confidence=1.0,
                savings_monthly=cost,
                message=f"Cancel {vendor}{detail}? I'll email them the cancellation.",
                action_prompt="Send the cancellation?",
                metadata={"vendor": vendor, "price": cost},
            )
        )
        return ""  # the alert itself is the reply

    if cmd.command == "negotiate":
        r = _renewal(cmd.vendor)
        price = float(r.get("monthly_cost") or 0) if r else 0.0
        if not price:
            return (
                f"I don't have contract details for {cmd.vendor}. Tell me the monthly price, e.g. 'negotiate "
                f"{cmd.vendor} at $500'."
            )
        vendor = r["vendor"]
        target = s.negotiation_default_target_pct
        seats = ""
        if r.get("seats_paid") and r.get("seats_active") is not None and r["seats_paid"] > r["seats_active"]:
            seats = f" {r['seats_paid'] - r['seats_active']} of {r['seats_paid']} seats are dormant, which helps us."
        await alerts.raise_alert(
            Finding(
                pillar="saas_sprawl",
                agent="command",
                alert_type="negotiate_offer",
                requires_action=True,
                confidence=1.0,
                savings_monthly=price * target / 100,
                message=f"{vendor} is ${price:,.0f}/mo and renews {r.get('renewal_date')}.{seats} I'll ask for {target:g}% "
                f"off (~${price * target / 100:,.0f}/mo) and handle the back-and-forth by email.",
                action_prompt=f"Start negotiating with {vendor}?",
                metadata={"vendor": vendor, "price": price, "target_pct": target},
            )
        )
        return ""

    if cmd.command == "downgrade":
        to = f" to {cmd.seats} seats" if cmd.seats else " to a cheaper plan"
        await alerts.raise_alert(
            Finding(
                pillar="saas_sprawl",
                agent="command",
                alert_type="downgrade_requested",
                requires_action=True,
                confidence=1.0,
                message=f"Downgrade {cmd.vendor}{to}? I'll email their billing team.",
                action_prompt="Send the downgrade request?",
                metadata={"vendor": cmd.vendor, "seats": cmd.seats},
            )
        )
        return ""

    if cmd.command in ("approve", "reject"):
        from runway.conversation import handle_yes_no

        return await handle_yes_no(cmd.command == "approve")

    if cmd.command == "show_pending":
        items = alerts.pending()
        if not items:
            return "Nothing waiting on you. 🎉"
        return "Waiting on you:\n" + "\n".join(f"{i + 1}. {a['message'][:90]}" for i, a in enumerate(items))

    if cmd.command == "stop_negotiation":
        n = engine.active_for(cmd.vendor or "")
        if not n:
            return "No active negotiation for that vendor."
        engine.cancel(n["id"])
        return f"Stopped the {n['vendor']} negotiation."

    if cmd.command == "update_policy" and cmd.policy and cmd.value is not None:
        field = {"days": "threshold_days", "percent": "threshold_discount_pct"}.get(cmd.unit or "", "threshold_amount")
        if not update_threshold(cmd.policy, field, int(cmd.value) if field == "threshold_days" else cmd.value):
            return "I couldn't find that policy."
        return f"Updated {cmd.policy.replace('_', ' ')}: {field.replace('_', ' ')} is now {cmd.value:g}."

    return "I didn't catch that. Text 'help' for what I can do."
