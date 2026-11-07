"""Decide which pillar a transaction belongs to.

Order: explicit category on the transaction -> known vendor list -> Claude (fast tier) -> unknown.
The known list makes the demo instant and free; Claude handles the long tail ("Joe's Diner",
"AWS Marketplace", "Replicate").
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from runway import llm
from runway.agents.compliance import flag_words
from runway.models import Pillar, TransactionIn

AI_VENDORS = {
    "anthropic",
    "openai",
    "replicate",
    "groq",
    "mistral",
    "cohere",
    "together ai",
    "fireworks",
    "perplexity",
    "elevenlabs",
    "bedrock",
}
SAAS_VENDORS = {
    "cursor",
    "notion",
    "figma",
    "linear",
    "slack",
    "vercel",
    "github",
    "zoom",
    "loom",
    "midjourney",
    "1password",
    "datadog",
    "sentry",
    "intercom",
    "mailchimp",
    "jira",
    "asana",
    "airtable",
    "hubspot",
    "evernote",
    "roam research",
    "miro",
    "canva",
    "dropbox",
    "google workspace",
}
CATEGORY_TO_PILLAR: dict[str, Pillar] = {
    "ai_spend": "ai_spend",
    "ai_api": "ai_spend",
    "saas": "saas_sprawl",
    "saas_sprawl": "saas_sprawl",
    "expense": "compliance",
    "compliance": "compliance",
}


class _Route(BaseModel):
    pillar: Literal["ai_spend", "saas_sprawl", "compliance", "unknown"]
    reason: str


def _has_word(text: str, word: str) -> bool:
    """Whole-word match, so "Bloomingdale's" is not Loom and "Get Together Bar" is not Together AI."""
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def known_pillar(txn: TransactionIn) -> Pillar | None:
    if txn.category and txn.category.lower() in CATEGORY_TO_PILLAR:
        return CATEGORY_TO_PILLAR[txn.category.lower()]
    m = txn.merchant.lower()
    if any(_has_word(m, v) for v in AI_VENDORS):
        return "ai_spend"
    if any(_has_word(m, v) for v in SAAS_VENDORS):
        return "saas_sprawl"
    return None


async def route(txn: TransactionIn) -> tuple[Pillar, str]:
    """Returns (pillar, short reason)."""
    if p := known_pillar(txn):
        return p, "known vendor"
    if txn.employee_id and flag_words(txn.merchant):
        return "compliance", "red-flag merchant on an employee card"

    out = await llm.structured(
        f"""Classify this company card charge into exactly one pillar.

Merchant: {txn.merchant}
Amount: ${txn.amount:g}
Submitted by: {txn.submitted_by}
Memo: {txn.memo or "none"}

Pillars:
- ai_spend: AI model/API providers (LLM APIs, inference platforms, GPU clouds billed per usage)
- saas_sprawl: software subscriptions billed per seat or plan
- compliance: employee expenses (meals, travel, hotels, retail, rideshare)
- unknown: none of the above, or genuinely ambiguous""",
        _Route,
        tier="fast",
    )
    if out and out.pillar == "unknown" and txn.employee_id:
        return "compliance", "employee card; the model was unsure"
    if out:
        return out.pillar, out.reason
    # No LLM: an employee charge is almost always an expense; otherwise ask the founder.
    if txn.employee_id:
        return "compliance", "employee card, no LLM available"
    return "unknown", "unrecognized merchant"
