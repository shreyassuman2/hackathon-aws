"""The restraint filter: decides whether a finding is worth interrupting the founder for.

Three tiers:
  urgent           send now, any hour
  decision_needed  send during the founder's business hours (08:00-21:00 local), otherwise hold
  informational    hold for the Monday brief / Friday digest
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from runway.config import get_settings
from runway.models import Finding

Tier = Literal["urgent", "decision_needed", "informational"]

BUSINESS_HOURS = (8, 21)
URGENT_FLAGS = {"fraud", "gambling", "adult", "cash_advance", "employee_disputed"}


def classify(f: Finding, amount: float = 0.0) -> tuple[Tier, str]:
    if f.spike_detected and f.pillar == "ai_spend":
        return "urgent", "AI cost spike (>2x last week)"
    if f.pillar == "compliance" and URGENT_FLAGS & set(f.flags):
        return "urgent", "possible fraud or serious policy violation"
    if f.below_policy_floor:
        return "urgent", "negotiation offer below the policy floor"
    if f.agent == "unclassified" and amount > 500:
        return "urgent", f"unknown merchant charge of ${amount:g}"

    if f.days_until_renewal is not None and f.days_until_renewal <= 7:
        return "decision_needed", f"renewal decision due in {f.days_until_renewal} day(s)"
    if f.agent == "unclassified" and amount > 200:
        return "decision_needed", f"unknown merchant ${amount:g} needs a one-time category"
    if f.requires_action and f.confidence >= 0.7:
        return "decision_needed", "action needs founder approval"

    return "informational", "routine; bundled into the digest"


def local_hour(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return (now.hour + get_settings().founder_tz_offset) % 24


def should_send_now(tier: Tier, now: datetime | None = None) -> bool:
    if tier == "urgent":
        return True
    if tier == "decision_needed":
        start, end = BUSINESS_HOURS
        return start <= local_hour(now) < end
    return False
