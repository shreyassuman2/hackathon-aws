"""Exercises the Bedrock code paths with a fake client (no AWS needed)."""

from types import SimpleNamespace as NS

import pytest

from runway import llm
from runway.agents import ask
from runway.config import get_settings


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    parse = create


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("RUNWAY_LLM", "bedrock")
    get_settings.cache_clear()

    def install(*responses):
        msgs = FakeMessages(responses)
        monkeypatch.setattr(llm, "_client", NS(messages=msgs))
        return msgs

    return install


def text(t, stop="end_turn"):
    return NS(stop_reason=stop, content=[NS(type="text", text=t)])


async def test_tool_loop_runs_tools_and_answers(seeded, fake):
    msgs = fake(
        NS(
            stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="upcoming_renewals", input={"days": 30})]
        ),
        text("Cursor renews soon."),
    )
    assert await ask.answer("what renews?") == "Cursor renews soon."
    tool_result = msgs.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and "Cursor" in tool_result["content"]
    assert msgs.calls[0]["output_config"] == {"effort": "low"}


async def test_refusal_and_errors_fall_back(seeded, fake):
    fake(text("", stop="refusal"))
    assert await llm.text("hi") is None
    fake(RuntimeError("throttled"))
    # Ask-Anything still answers from the deterministic path.
    assert "Renewing" in await ask.answer("which subs renew in 30 days")


async def test_haiku_45_gets_no_effort(fake, monkeypatch):
    monkeypatch.setenv("RUNWAY_MODEL_FAST", "anthropic.claude-haiku-4-5")
    get_settings.cache_clear()
    msgs = fake(text("ok"))
    await llm.text("hi", tier="fast")
    assert "output_config" not in msgs.calls[0]
