from runway import entities as E
from runway import pipeline, restraint
from runway.agents import router
from runway.models import Finding, TransactionIn

MARCUS = "00000001-0000-4000-8000-000000000011"


def test_known_vendor_routing():
    assert router.known_pillar(TransactionIn(merchant="Anthropic", amount=1)) == "ai_spend"
    assert router.known_pillar(TransactionIn(merchant="Figma", amount=1)) == "saas_sprawl"
    assert router.known_pillar(TransactionIn(merchant="Blue Bottle", amount=1)) is None


async def test_ai_spike_is_urgent(seeded):
    alert = await pipeline.process(TransactionIn(merchant="Anthropic", amount=4800))
    assert alert["pillar"] == "ai_spend" and alert["tier"] == "urgent" and alert["delivered"]


async def test_gambling_expense_is_urgent_and_asks_employee(seeded):
    # Old bug: compliance results had no `agent`, so they could never be urgent.
    alert = await pipeline.process(TransactionIn(merchant="Lucky Casino", amount=640, employee_id=MARCUS))
    assert alert["alert_type"] == "expense_flagged" and alert["tier"] == "urgent"
    assert seeded.list(E.EMPLOYEE_THREAD)


async def test_clean_expense_is_silent(seeded):
    alert = await pipeline.process(
        TransactionIn(merchant="Blue Bottle", amount=18, employee_id=MARCUS, memo="coffee w/ candidate")
    )
    assert alert["alert_type"] == "expense_ok" and alert["tier"] == "informational" and not alert["delivered"]


async def test_saas_renewal_offers_negotiation(seeded):
    alert = await pipeline.process(TransactionIn(merchant="Cursor", amount=1400))
    assert alert["alert_type"] == "negotiate_offer" and alert["metadata"]["price"] == 1400


def test_decision_needed_waits_for_business_hours(monkeypatch):
    from datetime import UTC, datetime

    from runway.config import get_settings

    monkeypatch.setenv("RUNWAY_FOUNDER_TZ_OFFSET", "0")
    get_settings.cache_clear()
    f = Finding(pillar="saas_sprawl", agent="saas", message="x", requires_action=True, confidence=0.9)
    tier, _ = restraint.classify(f)
    assert tier == "decision_needed"
    assert not restraint.should_send_now(tier, datetime(2026, 1, 1, 3, tzinfo=UTC))
    assert restraint.should_send_now(tier, datetime(2026, 1, 1, 10, tzinfo=UTC))


# ── matching and robustness fixes ─────────────────────────────────────────────


def test_vendor_matching_is_whole_word():
    from runway.agents.router import known_pillar
    from runway.models import TransactionIn

    def pillar(merchant):
        return known_pillar(TransactionIn(merchant=merchant, amount=10))

    assert pillar("Bloomingdale's") is None
    assert pillar("Cursor") == "saas_sprawl"
    assert pillar("Anthropic, PBC") == "ai_spend"


def test_red_flags_are_whole_word():
    from runway.agents.compliance import check
    from runway.models import TransactionIn

    def flags(merchant):
        return check(TransactionIn(merchant=merchant, amount=10, memo="x"), None)

    assert flags("Alphabet Inc") == []
    assert flags("Atmosphere Cafe") == []
    assert flags("Lucky Casino") == ["gambling"]
    assert flags("ATM Withdrawal") == ["cash_advance"]


def test_cap_counts_month_to_date_spend():
    from runway.agents.compliance import check
    from runway.models import TransactionIn

    txn = TransactionIn(merchant="Delta", amount=200, memo="flight")
    emp = {"monthly_expense_cap": 500}
    assert check(txn, emp, month_spend=0) == []
    assert check(txn, emp, month_spend=400) == ["over_cap:500"]


def test_employee_escalation_handles_curly_apostrophe():
    from runway.employees import ESCALATE_WORDS

    text = "I don’t know what that is".lower().replace("’", "'")
    assert any(w in text for w in ESCALATE_WORDS)


def test_grounding_rejects_invented_dollar_figures():
    from runway.agents.grounding import is_grounded

    source = "Charge: Cursor, $1400.00. potential_savings 308"
    assert is_grounded("Cursor billed $1,400; routing saves about $308/mo.", source)
    assert is_grounded("That is $3,696/yr.", source)
    assert not is_grounded("You could save $9,999 a month.", source)


async def test_ask_tools_cover_vendor_opportunities_and_pillars():
    from runway.agents import ask

    assert "vendor_opportunities" in {t.name for t in ask.TOOLS}
    out = await ask.spend_by_pillar(30)
    assert "by_pillar" in out
    assert (await ask.vendor_opportunities("Linear"))["vendor"] == "Linear"
