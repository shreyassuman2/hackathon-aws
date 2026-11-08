import pytest

from runway import conversation, digest, pipeline
from runway import entities as E
from runway.agents import commands
from runway.config import get_settings
from runway.models import TransactionIn

MARCUS = "00000001-0000-4000-8000-000000000011"


@pytest.fixture
def awake(monkeypatch):
    """Pretend it's business hours so decision_needed alerts are delivered immediately."""
    from runway import restraint

    monkeypatch.setattr(restraint, "should_send_now", lambda tier, now=None: tier != "informational")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("y", (True, None)),
        ("Yes!", (True, None)),
        ("N", (False, None)),
        ("y 2", (True, 2)),
        ("yes to #3", (True, 3)),
        ("no 1", (False, 1)),
        ("today", None),  # old bug: substring match made this a yes
        ("no way, what did we spend on AI?", None),
        ("yesterday's charges", None),
    ],
)
def test_parse_decision(text, expected):
    assert conversation.parse_decision(text) == expected


@pytest.mark.parametrize(
    ("text", "kind", "vendor", "pct"),
    [
        ("cancel Notion", "cancel", "notion", None),
        ("Cancel our Evernote subscription.", "cancel", "evernote", None),
        ("negotiate Cursor", "negotiate", "cursor", None),
        ("negotiate cursor to 25%", "negotiate", "cursor", 25),
        ("stop negotiating with Cursor", "stop_negotiation", "cursor", None),
        ("show pending", "pending", None, None),
        ("UNDO", "undo", None, None),
        ("help", "help", None, None),
    ],
)
def test_parse_commands(text, kind, vendor, pct):
    cmd = commands.parse_quick(text)
    assert cmd is not None and cmd.kind == kind and cmd.vendor == vendor and cmd.pct == pct


def test_questions_are_not_commands():
    assert commands.parse_quick("what did we spend on AI last month?") is None
    assert commands.parse_quick("which subs renew soon") is None


async def test_yes_on_renewal_alert_starts_negotiation(seeded, awake):
    alert = await pipeline.process(TransactionIn(merchant="Cursor", amount=1400))
    assert alert["alert_type"] == "negotiate_offer" and alert["delivered"]
    out = await conversation.handle_inbound("y")
    assert out["handled_as"] == "founder"
    assert seeded.get(E.ALERT, alert["id"])["founder_action"] == "Y"
    negs = seeded.list(E.NEGOTIATION)
    assert len(negs) == 1 and negs[0]["vendor"] == "Cursor" and negs[0]["status"] == "waiting"
    assert negs[0]["alert_id"] == alert["id"]


async def test_no_resolves_without_acting(seeded, awake):
    alert = await pipeline.process(TransactionIn(merchant="Cursor", amount=1400))
    out = await conversation.handle_inbound("nope")
    assert seeded.get(E.ALERT, alert["id"])["founder_action"] == "N"
    assert not seeded.list(E.NEGOTIATION) and out["reply"]


async def test_numbered_reply_picks_from_pending_list(seeded):
    rows = commands.pending_lines()
    assert len(rows) >= 2
    await conversation.handle_inbound("n 2")
    assert seeded.get(E.ALERT, rows[1]["id"])["founder_action"] == "N"
    assert not seeded.get(E.ALERT, rows[0]["id"]).get("resolved")


async def test_yes_with_nothing_pending(env):
    out = await conversation.handle_inbound("y")
    assert "Nothing is waiting" in out["reply"]


async def test_cancel_command_marks_savings(seeded):
    out = await conversation.handle_inbound("cancel Notion")
    assert "Notion" in out["reply"] and "$480/mo" in out["reply"]
    renewal = next(r for r in seeded.list(E.RENEWAL) if r["vendor"] == "Notion")
    assert renewal["status"] == "cancelled"
    assert any(s["title"] == "Cancel Notion" for s in seeded.list(E.SAVINGS))


async def test_negotiate_command_sends_opening(seeded):
    out = await conversation.handle_inbound("negotiate Cursor to 25%")
    assert out["reply"] is None  # the engine already texted "Sent Cursor our ask"
    neg = seeded.list(E.NEGOTIATION)[0]
    assert neg["target_pct"] == 25 and neg["round"] == 1 and all(o["sent"] for o in neg["outbox"])
    again = await conversation.handle_inbound("negotiate cursor")
    assert "Already negotiating" in again["reply"]


async def test_undo_reverses_auto_cancel(seeded):
    from runway import policies

    seeded.put(E.SEAT, {"tool": "Loom", "last_active_date": "2020-01-01", "is_dormant": True})
    seeded.put(E.RENEWAL, {"vendor": "Loom", "monthly_cost": 15, "renewal_date": "2099-01-01"})
    assert policies.auto_cancel("Loom", 15) is not None
    out = await conversation.handle_inbound("undo")
    assert "Loom is back on" in out["reply"]
    assert all(a.get("undone") for a in seeded.list(E.POLICY_ACTION) if a["entity_name"] == "Loom")


async def test_question_goes_to_ask_anything(seeded):
    out = await conversation.handle_inbound("which subs renew in the next 30 days?")
    assert out["handled_as"] == "founder" and out["reply"]


async def test_employee_reply_is_routed_to_thread(seeded, monkeypatch):
    monkeypatch.setenv("RUNWAY_FOUNDER_PHONE", "+15559990000")
    get_settings.cache_clear()
    await pipeline.process(TransactionIn(merchant="Lucky Casino", amount=640, employee_id=MARCUS))
    phone = seeded.get(E.EMPLOYEE, MARCUS)["phone"]
    out = await conversation.handle_inbound("that's not mine", sender=phone)
    assert out["handled_as"] == "employee" and out["status"] == "escalated"


async def test_digest_bundles_held_items_once(seeded):
    await pipeline.process(TransactionIn(merchant="Blue Bottle", amount=18, employee_id=MARCUS, memo="coffee"))
    first = await digest.send("weekly")
    assert first["sent"] and first["items"] >= 1 and "Blue Bottle" in first["text"]
    second = await digest.send("weekly")
    assert second["items"] == 0


async def test_bare_yes_ignored_unless_runway_just_asked(seeded, awake):
    alert = await pipeline.process(TransactionIn(merchant="Cursor", amount=1400))
    await conversation.handle_inbound("what did we spend on AI last month")  # Runway's last text is an answer
    out = await conversation.handle_inbound("y")
    assert "not waiting on a yes or no" in out["reply"]
    assert not seeded.get(E.ALERT, alert["id"]).get("resolved") and not seeded.list(E.NEGOTIATION)


async def test_numbered_yes_still_counts_without_a_fresh_question(seeded):
    rows = commands.pending_lines()
    await conversation.handle_inbound("y 1")
    assert seeded.get(E.ALERT, rows[0]["id"])["founder_action"] == "Y"
