"""Negotiation brains: classify a vendor reply, decide the next move, draft the email.

`decide()` is a pure function of (state, classification), so the strategy is unit-testable
without any LLM. Claude is used for two things only: reading ambiguous replies, and writing
emails that sound human. Both have deterministic fallbacks.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from runway import llm

ReplyKind = Literal["accept", "counter", "reject", "stall", "irrelevant"]
Action = Literal["accept", "counter", "walk_away", "ask_founder", "wait"]

LEVERAGE = {
    "competitive_alternatives": "we're evaluating competitive alternatives",
    "annual_commitment": "we can commit to an annual term if the price is right",
    "budget_constraints": "we're operating under a strict budget this year",
    "seat_reduction": "we'll reduce seats if the price doesn't move",
}


class Classification(BaseModel):
    kind: ReplyKind
    offer_pct: float | None = Field(default=None, description="Discount % the vendor is offering, if any")
    is_final: bool = Field(default=False, description="Vendor says this is their best/final/maximum offer")
    confidence: float = 0.5
    reasoning: str = ""


@dataclass
class Move:
    action: Action
    ask_pct: float | None = None
    reason: str = ""
    below_floor: bool = False


# ── classification ────────────────────────────────────────────────────────────

_PCT = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?%")
# Firm acceptance only. "Let me know if you'd like to proceed" is NOT acceptance.
_ACCEPT = (
    "we've agreed",
    "we have agreed",
    "agreed to",
    "we can confirm",
    "confirmed",
    "match your ask",
    "we accept",
    "happy to accept",
    "approved your",
    "deal.",
)
_REJECT = (
    "unable to offer",
    "cannot offer",
    "can't offer",
    "no discount",
    "not able to discount",
    "pricing is standardized",
    "not possible",
    "won't be able",
)
_FINAL = (
    "maximum",
    "best we can",
    "best i can",
    "final offer",
    "highest we can",
    "can't go further",
    "cannot go further",
    "as far as we can",
)
_STALL = ("reviewing", "discuss internally", "get back to you", "let me check", "loop in", "circle back")


def heuristic_classify(text: str) -> Classification:
    low = text.lower()
    pcts = [float(p) for p in _PCT.findall(text)]
    offer = max(pcts) if pcts else None
    final = any(w in low for w in _FINAL)
    if offer is not None and any(w in low for w in _ACCEPT):
        return Classification(kind="accept", offer_pct=offer, confidence=0.85, reasoning="firm acceptance language")
    if offer is None and any(w in low for w in _REJECT):
        return Classification(kind="reject", confidence=0.8, reasoning="declined, no number offered")
    if offer is not None:
        return Classification(
            kind="counter",
            offer_pct=offer,
            is_final=final,
            confidence=0.75,
            reasoning=f"offered {offer:g}%" + (" (says it's final)" if final else ""),
        )
    if any(w in low for w in _STALL):
        return Classification(kind="stall", confidence=0.6, reasoning="needs internal review")
    return Classification(kind="irrelevant", confidence=0.3, reasoning="no offer or decision found")


async def classify(text: str, state: dict[str, Any]) -> Classification:
    out = await llm.structured(
        f"""Classify a vendor's reply in a SaaS renewal negotiation.

We asked for {state["target_pct"]:g}% off. Our floor is {state["floor_pct"]:g}%.
Round: {state["round"]}. Their previous offer: {state.get("current_offer_pct")}.

Reply:
<<<
{text}
>>>

kind:
- accept: they firmly agreed to a specific discount (conditional phrasing like "if you'd like to
  proceed" is NOT acceptance; that's a counter)
- counter: they offered a specific discount that isn't a firm agreement
- reject: they declined with no number
- stall: they need time or internal review
- irrelevant: auto-reply or unrelated
Set is_final if they say it's their best/maximum/final offer.""",
        Classification,
        tier="fast",
    )
    return out or heuristic_classify(text)


# ── strategy ──────────────────────────────────────────────────────────────────


def next_ask(target: float, offer: float | None, round_no: int) -> float:
    """Hold the target on the first counter, then meet halfway (rounded up), never below their offer + 1."""
    if offer is None or round_no <= 1:
        return target
    return min(target, max(offer + 1, math.ceil((offer + target) / 2)))


def decide(state: dict[str, Any], c: Classification, *, max_rounds: int, policy_allows_accept: bool) -> Move:
    target, floor = float(state["target_pct"]), float(state["floor_pct"])
    offer = c.offer_pct
    below = offer is not None and offer < floor

    if c.kind == "accept":
        return Move("accept", offer, "vendor accepted")
    if c.kind == "reject":
        return Move("walk_away", None, "vendor declined outright")
    if c.kind in ("stall", "irrelevant"):
        return Move("wait", None, c.reasoning)

    # counter
    if offer is not None and offer >= target:
        return Move("accept", offer, f"{offer:g}% meets our {target:g}% target")
    if c.is_final:
        if not below and policy_allows_accept:
            return Move("accept", offer, f"final offer {offer:g}% is within the auto-accept policy")
        return Move("ask_founder", offer, f"vendor's final offer is {offer:g}%", below_floor=below)
    if state["round"] >= max_rounds:
        return Move("ask_founder", offer, f"{state['round']} rounds without agreement", below_floor=below)
    return Move("counter", next_ask(target, offer, state["round"]), f"countering their {offer:g}%", below_floor=below)


def pick_leverage(used: list[str], n: int = 2) -> list[str]:
    fresh = [k for k in LEVERAGE if k not in used]
    return (fresh or ["budget_constraints"])[:n]


# ── drafting ──────────────────────────────────────────────────────────────────


def _price(state: dict[str, Any], pct: float) -> str:
    return f"${float(state['original_price']) * (1 - pct / 100):,.0f}/mo"


def _history(state: dict[str, Any], n: int = 4) -> str:
    return "\n".join(
        f"[{'US' if m['direction'] == 'out' else 'VENDOR'}] {m['body'][:400]}" for m in state.get("thread", [])[-n:]
    )


SYSTEM = (
    "You write renewal negotiation emails on behalf of a startup founder. Plain text, no subject line, "
    'no placeholders like [Name]. Sign off as "{signoff}". Firm, warm, brief.'
)


async def draft_opening(state: dict[str, Any], leverage: list[str], signoff: str) -> str:
    t = float(state["target_pct"])
    text = await llm.text(
        f"""Write the opening email to {state["vendor"]} about our renewal.
Current price: ${float(state["original_price"]):,.0f}/mo. Ask: {t:g}% off ({_price(state, t)}).
Points to make: {[LEVERAGE[k] for k in leverage]}.
Past negotiations that worked, for tone: {state.get("reference_wins") or "none"}.
Two short paragraphs and a clear ask.""",
        system=SYSTEM.format(signoff=signoff),
    )
    return text or (
        f"Hi {state['vendor']} team,\n\n"
        f"We're reviewing renewals across our stack. We're at ${float(state['original_price']):,.0f}/mo with you "
        f"today, and {LEVERAGE[leverage[0]]}. To renew, we need {t:g}% off ({_price(state, t)}).\n\n"
        f"If that works, please send an updated quote and we can sign quickly.\n\nThanks,\n{signoff}"
    )


async def draft_counter(
    state: dict[str, Any], offer: float | None, ask: float, leverage: list[str], signoff: str
) -> str:
    text = await llm.text(
        f"""Write our counter-offer reply to {state["vendor"]}.
They offered {offer}% off. We are asking for {ask:g}% ({_price(state, ask)}).
New points to make (don't repeat earlier ones): {[LEVERAGE[k] for k in leverage]}.
Thread so far:
{_history(state)}
Acknowledge their movement, hold firm on {ask:g}%, two short paragraphs.""",
        system=SYSTEM.format(signoff=signoff),
    )
    return text or (
        f"Hi {state['vendor']} team,\n\nThanks for coming back with {offer:g}%. We appreciate the movement, but "
        f"{LEVERAGE[leverage[0]]}, and we need {ask:g}% ({_price(state, ask)}) to commit.\n\n"
        f"If you can get to {ask:g}%, we're ready to sign an annual term this week.\n\nThanks,\n{signoff}"
    )


def draft_acceptance(state: dict[str, Any], pct: float, signoff: str) -> str:
    return (
        f"Hi {state['vendor']} team,\n\nThat works for us: {pct:g}% off ({_price(state, pct)}). Please send "
        f"the updated contract and we'll get it signed.\n\nThanks,\n{signoff}"
    )
