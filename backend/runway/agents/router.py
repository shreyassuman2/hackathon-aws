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
    "codex",
    "chatgpt",
    "claude",
    "gemini",
    "openrouter",
    "deepseek",
    "hugging face",
    "runpod",
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


def _one_edit_apart(a: str, b: str) -> bool:
    """True when a and b differ by exactly one inserted, deleted or substituted character."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return edits + (len(b) - j) == 1


def _typo_of(merchant: str) -> tuple[Pillar, str] | None:
    """A one-letter typo of a known single-word vendor ("vercil" -> Vercel), or None.

    Kept narrow so near-miss names of other companies don't get routed: words of 5+ letters only,
    the same first letter (so "Motion" is not Notion), and exactly one edit away.
    """
    words = re.findall(r"[a-z0-9]+", merchant)
    for pillar, vendors in (("ai_spend", AI_VENDORS), ("saas_sprawl", SAAS_VENDORS)):
        for v in vendors:
            if " " in v or len(v) < 5:
                continue
            if any(len(w) >= 5 and w[0] == v[0] and _one_edit_apart(w, v) for w in words):
                return pillar, v  # type: ignore[return-value]
    return None


def match_vendor(txn: TransactionIn) -> tuple[Pillar, str] | None:
    """(pillar, reason) from the transaction's category or the known vendor lists, typos included."""
    if txn.category and txn.category.lower() in CATEGORY_TO_PILLAR:
        return CATEGORY_TO_PILLAR[txn.category.lower()], "category given"
    m = txn.merchant.lower()
    if any(_has_word(m, v) for v in AI_VENDORS):
        return "ai_spend", "known vendor"
    if any(_has_word(m, v) for v in SAAS_VENDORS):
        return "saas_sprawl", "known vendor"
    if typo := _typo_of(m):
        pillar, vendor = typo
        return pillar, f"looks like {vendor.title()} (one letter off)"
    return None


def known_pillar(txn: TransactionIn) -> Pillar | None:
    match = match_vendor(txn)
    return match[0] if match else None


async def route(txn: TransactionIn) -> tuple[Pillar, str]:
    """Returns (pillar, short reason)."""
    if match := match_vendor(txn):
        return match
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
