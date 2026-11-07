import pytest

from runway import alerts, conversation
from runway.models import Finding


@pytest.mark.parametrize(
    "text,expected",
    [
        ("y", True),
        ("Yes!", True),
        ("ok do it", True),
        ("sounds good", True),
        ("n", False),
        ("no, skip it today", False),
        ("nope", False),
        ("yesterday's bill?", None),
        ("what did we spend on AI", None),
        ("not sure what this is, explain", None),
    ],
)
def test_yes_or_no(text, expected):
    # Old bug: substring matching made "no, skip it today" a YES (the "y" in "today").
    assert conversation.yes_or_no(text) is expected


async def test_yes_resolves_latest_pending(env):
    await alerts.raise_alert(
        Finding(
            pillar="saas_sprawl",
            agent="t",
            alert_type="downgrade_requested",
            message="first",
            requires_action=True,
            action_prompt="?",
            confidence=1,
            spike_detected=False,
            metadata={"vendor": "Old"},
        )
    )
    await alerts.raise_alert(
        Finding(
            pillar="saas_sprawl",
            agent="t",
            alert_type="cancel_requested",
            message="second",
            requires_action=True,
            action_prompt="?",
            below_policy_floor=True,
            metadata={"vendor": "Notion", "price": 480},
        )
    )
    out = await conversation.handle_inbound("", "Y")
    assert "Notion" in out["reply"]
    assert [a["message"] for a in alerts.pending()] == ["first"]


async def test_menu_and_questions(seeded):
    assert (await conversation.handle_inbound("", "help"))["status"] == "menu"
    out = await conversation.handle_inbound("", "which subs renew in the next 30 days?")
    assert out["status"] == "question" and "Cursor" in out["reply"]


async def test_employee_reply_routed_by_normalized_phone(seeded, monkeypatch):
    from runway.config import get_settings

    monkeypatch.setenv("RUNWAY_FOUNDER_PHONE", "(415) 555-0199")
    get_settings.cache_clear()
    # Founder number in a different format is still the founder.
    assert (await conversation.handle_inbound("+14155550199", "help"))["status"] == "menu"
    # An employee with no open thread gets routed to the employee handler, not treated as founder.
    assert (await conversation.handle_inbound("+15550100001", "y"))["status"] == "no_open_thread"
