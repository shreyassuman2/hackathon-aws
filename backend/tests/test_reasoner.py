import pytest

from runway.negotiation.reasoner import Classification, decide, heuristic_classify, next_ask

STATE = {"target_pct": 20.0, "floor_pct": 5.0, "round": 1, "original_price": 1000.0}


@pytest.mark.parametrize(
    "text,kind,pct",
    [
        ("We can offer 12% off if you commit annually. Let me know if you'd like to proceed.", "counter", 12),
        ("We've agreed to your requested 20% discount. Confirmed.", "accept", 20),
        ("Unfortunately we're unable to offer discounts. Pricing is standardized.", "reject", None),
        ("Let me discuss internally and get back to you.", "stall", None),
        ("I'm out of office until Monday.", "irrelevant", None),
    ],
)
def test_heuristic_classify(text, kind, pct):
    c = heuristic_classify(text)
    assert c.kind == kind
    assert c.offer_pct == pct


def test_proceed_is_not_acceptance():
    # Old bug: "proceed" + a number was treated as the vendor accepting.
    assert heuristic_classify("12% off. Shall we proceed?").kind == "counter"


def test_final_offer_detected():
    c = heuristic_classify("18% is the maximum I'm able to offer at this tier.")
    assert c.kind == "counter" and c.is_final


def test_decide_counter_then_concede():
    c = Classification(kind="counter", offer_pct=10)
    assert decide(STATE, c, max_rounds=4, policy_allows_accept=False).action == "counter"
    assert next_ask(20, 10, 1) == 20  # hold target on the first counter
    assert next_ask(20, 18, 2) == 19  # then meet partway
    assert next_ask(20, 19.5, 3) == 20


def test_decide_accepts_offer_meeting_target():
    m = decide(STATE, Classification(kind="counter", offer_pct=25), max_rounds=4, policy_allows_accept=False)
    assert m.action == "accept" and m.ask_pct == 25


def test_decide_final_offer_goes_to_founder_unless_policy_allows():
    c = Classification(kind="counter", offer_pct=15, is_final=True)
    assert decide(STATE, c, max_rounds=4, policy_allows_accept=False).action == "ask_founder"
    assert decide(STATE, c, max_rounds=4, policy_allows_accept=True).action == "accept"


def test_decide_below_floor_flags_founder():
    c = Classification(kind="counter", offer_pct=3, is_final=True)
    m = decide(STATE, c, max_rounds=4, policy_allows_accept=True)
    assert m.action == "ask_founder" and m.below_floor


def test_decide_escalates_after_max_rounds():
    m = decide(
        {**STATE, "round": 4}, Classification(kind="counter", offer_pct=12), max_rounds=4, policy_allows_accept=False
    )
    assert m.action == "ask_founder"
