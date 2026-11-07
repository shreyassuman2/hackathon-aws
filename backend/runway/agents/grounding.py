"""Guard against invented numbers: every dollar figure in an LLM message must come from the data."""

from __future__ import annotations

import logging
import re

log = logging.getLogger("runway.grounding")

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?([kK])?")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def dollar_figures(message: str) -> list[float]:
    return [_to_float(n) * (1000 if k else 1) for n, k in _MONEY.findall(message)]


def is_grounded(message: str, source: str) -> bool:
    """True if each $ figure in `message` appears in `source` (±$1), or is a 12x annualization of one."""
    allowed = [_to_float(n) for n in _NUM.findall(source)]
    allowed += [a * 12 for a in allowed]
    return all(any(abs(fig - a) <= 1 for a in allowed) for fig in dollar_figures(message))


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def strip_trailing_question(message: str) -> str:
    """Drop a final question: the approval prompt is added separately, so a second one is ambiguous."""
    parts = _SENTENCE_END.split(message.strip())
    while len(parts) > 1 and parts[-1].rstrip().endswith("?"):
        parts.pop()
    return " ".join(parts)


def checked(message: str | None, source: str, agent: str) -> str | None:
    """Return the LLM message if its dollar figures come from the data, else None (use the template)."""
    if not message:
        return None
    if not is_grounded(message, source):
        log.warning("%s: LLM message rejected, figures not in the data: %s", agent, message[:200])
        return None
    return strip_trailing_question(message)
