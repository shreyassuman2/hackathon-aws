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


def test_trailing_question_is_stripped_and_ungrounded_message_rejected():
    from runway.agents.grounding import checked, strip_questions

    assert strip_questions("Save $800/mo. Renews Nov 13. Want me to act?") == "Save $800/mo. Renews Nov 13."
    assert strip_questions("Only a question?") == "Only a question?"
    assert strip_questions("No data. Can you check the sync? Will retry.") == "No data. Will retry."
    assert checked("Save $800/mo. Want me to act?", "saving 800", "t") == "Save $800/mo."
    assert checked("Save $9,999/mo.", "saving 800", "t") is None
    assert checked(None, "x", "t") is None


def test_cap_message_says_monthly_total():
    from runway.agents.compliance import _describe

    assert _describe("over_cap:500", 725) == "$725 this month, over the $500 monthly cap"


async def test_red_flag_merchant_on_employee_card_routes_to_compliance():
    from runway.agents.router import route
    from runway.models import TransactionIn

    pillar, _ = await route(TransactionIn(merchant="Lucky Casino", amount=300, employee_id="e1"))
    assert pillar == "compliance"


def test_asking_sentences_without_question_mark_are_stripped():
    from runway.agents.grounding import strip_questions

    msg = "Save $2,840/month. Want me to pull a comparison first, or ready to move forward."
    assert strip_questions(msg) == "Save $2,840/month."


async def test_ask_answer_never_ends_with_an_offer(monkeypatch):
    from runway import llm
    from runway.agents import ask

    async def fake(*a, **k):
        return "AI spend is $9,960 in the last 30 days. Want me to break it down by vendor?"

    monkeypatch.setattr(llm, "tool_chat", fake)
    assert await ask.answer("what did we spend on AI") == "AI spend is $9,960 in the last 30 days."


async def test_vendor_opportunities_warns_against_summing():
    from runway.agents import ask

    out = await ask.vendor_opportunities("Figma")
    assert "do not add them up" in out["note"]


def test_notice_status_flags_a_passed_deadline():
    from datetime import date

    from runway.agents.ask import notice_status

    today = date(2026, 11, 7)
    late = notice_status("2026-11-13", 14, today)
    assert late == {"cancel_by": "2026-10-30", "days_left_to_cancel": -8, "notice_window_passed": True}
    assert notice_status("2026-12-04", 30, today)["notice_window_passed"] is True  # cancel-by was Nov 4
    assert notice_status("2026-12-31", 30, today)["notice_window_passed"] is False
    assert notice_status(None, 14, today) == {}


async def test_spend_by_pillar_includes_top_vendors():
    from runway.agents import ask

    out = await ask.spend_by_pillar(36500)
    assert set(out["top_vendors"]) == set(out["by_pillar"])
    assert all(len(v) <= 3 for v in out["top_vendors"].values())


def test_router_catches_one_letter_typos_and_new_ai_tools():
    from runway.agents.router import known_pillar, match_vendor
    from runway.models import TransactionIn

    def pillar(merchant):
        return known_pillar(TransactionIn(merchant=merchant, amount=10))

    # What the card terminal sent: a typo of Vercel and OpenAI's Codex.
    assert pillar("vercil") == "saas_sprawl"
    assert match_vendor(TransactionIn(merchant="vercil", amount=10))[1] == "looks like Vercel (one letter off)"
    assert pillar("codeX") == "ai_spend"
    assert pillar("ChatGPT Plus") == "ai_spend"
    assert pillar("claude.ai") == "ai_spend"
    assert pillar("Vercel") == "saas_sprawl"  # exact names still win
    assert match_vendor(TransactionIn(merchant="Vercel", amount=10))[1] == "known vendor"

    # Near misses that are other companies must not be routed.
    assert pillar("Motion") is None  # not Notion: different first letter
    assert pillar("Sigma") is None  # not Figma
    assert pillar("Coherent") is None  # not Cohere: two letters off
    assert pillar("Bloom") is None  # Loom is too short to typo-match
    assert pillar("Verclle") is None  # two edits


async def test_typo_merchant_goes_to_its_pillar_not_unknown(seeded):
    alert = await pipeline.process(TransactionIn(merchant="vercil", amount=1500))
    assert alert["pillar"] == "saas_sprawl" and alert["alert_type"] != "categorize"
