"""Shared types passed between the pipeline, agents and API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Pillar = Literal["ai_spend", "saas_sprawl", "compliance", "unknown"]


class TransactionIn(BaseModel):
    """A card charge as it arrives from the bank feed / purchase emulator."""

    id: str | None = None
    merchant: str
    amount: float
    submitted_by: str = "system"
    employee_id: str | None = None
    memo: str | None = None
    category: str | None = None


class Finding(BaseModel):
    """What a specialist agent (or a policy) concluded about one transaction.

    The pipeline turns a Finding into an alert, runs it through the restraint filter,
    and maybe texts the founder.
    """

    pillar: Pillar
    agent: str  # which agent/policy produced this, e.g. "ai_spend", "policy.auto_cancel"
    message: str  # founder-facing text
    alert_type: str = "finding"
    requires_action: bool = False
    action_prompt: str | None = None
    autonomous: bool = False  # True when a policy already acted without asking
    confidence: float = 1.0
    savings_monthly: float = 0.0

    # Signals the restraint filter looks at
    spike_detected: bool = False
    flags: list[str] = Field(default_factory=list)
    days_until_renewal: int | None = None
    below_policy_floor: bool = False

    # Anything an approval needs to act later (vendor, price, target_pct, ...)
    metadata: dict[str, Any] = Field(default_factory=dict)
