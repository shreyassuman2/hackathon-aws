"""The one place Runway talks to Claude (on Amazon Bedrock).

Rules:
  * Agents never import `anthropic` directly. They call `text()`, `structured()` or `tool_chat()`.
  * Every call returns None when the LLM is off, refuses, or fails. Callers ALWAYS have a
    deterministic fallback, so the demo works with no AWS credentials at all.
  * Two tiers: "fast" (classification, routing) and "smart" (analysis, drafting, chat).
    The model IDs live in config (RUNWAY_MODEL_FAST / RUNWAY_MODEL_SMART).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from runway.config import get_settings

log = logging.getLogger("runway.llm")

Tier = Literal["fast", "smart"]

# Effort per tier: classification doesn't benefit from deep thinking; drafting does a bit.
_EFFORT: dict[Tier, str] = {"fast": "low", "smart": "medium"}
_MAX_TOKENS: dict[Tier, int] = {"fast": 1024, "smart": 4096}

_client = None


def enabled() -> bool:
    return get_settings().llm == "bedrock"


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropicBedrockMantle

        _client = AsyncAnthropicBedrockMantle(aws_region=get_settings().aws_region, max_retries=2, timeout=60.0)
    return _client


def _model(tier: Tier) -> str:
    s = get_settings()
    return s.model_fast if tier == "fast" else s.model_smart


def _effort(model: str, effort: str) -> dict[str, Any]:
    """`effort` isn't accepted by Haiku 4.5 (the open-access fallback model), so only send it when supported."""
    return {} if "haiku-4-5" in model else {"output_config": {"effort": effort}}


def _text_of(response: Any) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


async def text(
    prompt: str, *, system: str | None = None, tier: Tier = "smart", max_tokens: int | None = None
) -> str | None:
    """Free-form text completion. None means "use your fallback"."""
    if not enabled():
        return None
    try:
        resp = await _get_client().messages.create(
            model=_model(tier),
            max_tokens=max_tokens or _MAX_TOKENS[tier],
            system=system or "",
            **_effort(_model(tier), _EFFORT[tier]),
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # network / auth / throttling: degrade, don't crash the request
        log.warning("llm.text failed (%s): %s", tier, exc)
        return None
    if resp.stop_reason == "refusal":
        log.warning("llm.text refused (%s)", tier)
        return None
    return _text_of(resp) or None


async def structured[M: BaseModel](
    prompt: str, schema: type[M], *, system: str | None = None, tier: Tier = "fast"
) -> M | None:
    """Ask for JSON matching a Pydantic model (structured outputs, validated by the SDK)."""
    if not enabled():
        return None
    try:
        resp = await _get_client().messages.parse(
            model=_model(tier),
            max_tokens=_MAX_TOKENS[tier],
            system=system or "",
            **_effort(_model(tier), _EFFORT[tier]),
            output_format=schema,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        log.warning("llm.structured failed (%s): %s", schema.__name__, exc)
        return None
    if resp.stop_reason == "refusal":
        return None
    return resp.parsed_output


# ── Tool use (used by Ask-Anything) ───────────────────────────────────────────


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Awaitable[Any]]

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


async def tool_chat(
    messages: list[dict[str, Any]],
    tools: list[Tool],
    *,
    system: str,
    max_turns: int = 6,
) -> str | None:
    """Run a manual tool-use loop: Claude picks tools, we execute them, repeat until it answers."""
    if not enabled():
        return None
    by_name = {t.name: t for t in tools}
    convo = list(messages)
    client = _get_client()
    for _ in range(max_turns):
        try:
            resp = await client.messages.create(
                model=_model("smart"),
                max_tokens=_MAX_TOKENS["smart"],
                system=system,
                **_effort(_model("smart"), "low"),
                tools=[t.spec() for t in tools],
                messages=convo,
            )
        except Exception as exc:
            log.warning("llm.tool_chat failed: %s", exc)
            return None
        if resp.stop_reason == "refusal":
            return None
        if resp.stop_reason != "tool_use":
            return _text_of(resp) or None

        # Keep the full assistant content (including thinking blocks) in history.
        convo.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool = by_name.get(block.name)
            try:
                if tool is None:
                    raise ValueError(f"unknown tool {block.name}")
                out = await tool.fn(**(block.input or {}))
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)[:20000]}
                )
            except Exception as exc:
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": f"error: {exc}", "is_error": True}
                )
        # All results for one assistant turn go back in a single user message.
        convo.append({"role": "user", "content": results})
    return None
