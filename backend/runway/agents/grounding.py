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


def ungrounded_figures(message: str, source: str) -> list[float]:
    """$ figures in `message` that appear nowhere in `source` (±$1) and aren't a 12x annualization."""
    allowed = [_to_float(n) for n in _NUM.findall(source)]
    allowed += [a * 12 for a in allowed]
    return [fig for fig in dollar_figures(message) if not any(abs(fig - a) <= 1 for a in allowed)]


def is_grounded(message: str, source: str) -> bool:
    return not ungrounded_figures(message, source)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def strip_questions(message: str) -> str:
    """Drop question sentences: the approval prompt is added separately, so a second one is ambiguous."""
    parts = _SENTENCE_END.split(message.strip())
    kept = [p for p in parts if not p.rstrip().endswith("?")]
    return " ".join(kept) if kept else message.strip()


def checked(message: str | None, source: str, agent: str) -> str | None:
    """Return the LLM message if its dollar figures come from the data, else None (use the template)."""
    if not message:
        return None
    if bad := ungrounded_figures(message, source):
        log.warning("%s: LLM message rejected, figures not in the data %s: %s", agent, bad, message[:300])
        return None
    return strip_questions(message)
