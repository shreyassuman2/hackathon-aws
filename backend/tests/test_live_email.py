"""Live negotiation email must never reach a real company by accident."""

import pytest

from runway import entities as E
from runway.config import get_settings
from runway.negotiation import engine, mail

TEST_INBOX = "vendor-player@example.com"


@pytest.fixture
def live(monkeypatch):
    """Live mail with a fake SES client that records every send."""
    monkeypatch.setenv("RUNWAY_MAIL", "live")
    monkeypatch.setenv("RUNWAY_EMAIL_FROM", "runway@example.com")
    get_settings.cache_clear()
    sent: list[dict] = []

    class FakeSES:
        def send_email(self, **kw):
            sent.append(kw)

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeSES())
    return sent


def _override(monkeypatch, value=TEST_INBOX):
    monkeypatch.setenv("RUNWAY_VENDOR_EMAIL_OVERRIDE", value)
    get_settings.cache_clear()


def test_live_without_vendor_email_or_override_falls_back_to_demo(seeded, live):
    # This is the "founder texts y" path: no vendor_email. It must NOT email renewals@cursor.com.
    neg, _ = engine.start("Cursor", 1400)
    assert neg["demo"] is True
    assert any("NOT emailing renewals@cursor.com" in line for line in neg["log"])


def test_override_redirects_and_stays_live(seeded, live, monkeypatch):
    _override(monkeypatch)
    neg, _ = engine.start("Cursor", 1400)
    assert neg["demo"] is False and neg["vendor_email"] == TEST_INBOX


def test_override_wins_over_an_explicit_vendor_email(seeded, live, monkeypatch):
    _override(monkeypatch)
    neg, _ = engine.start("Cursor", 1400, vendor_email="sales@cursor.com")
    assert neg["vendor_email"] == TEST_INBOX


def test_explicit_vendor_email_without_override_is_used(seeded, live):
    neg, _ = engine.start("Cursor", 1400, vendor_email="teammate@example.com")
    assert neg["demo"] is False and neg["vendor_email"] == "teammate@example.com"


def test_send_redirects_even_for_deals_started_before_the_override(live, monkeypatch):
    _override(monkeypatch)
    assert mail.send("renewals@cursor.com", "s", "b", demo=False)
    assert live[0]["Destination"]["ToAddresses"] == [TEST_INBOX]


async def test_full_live_negotiation_only_ever_emails_the_test_inbox(seeded, live, monkeypatch):
    _override(monkeypatch)
    replies = iter(
        [
            [mail.Incoming("101", TEST_INBOX, "Re: Cursor renewal: pricing", "We can do 12% on an annual plan.")],
            [mail.Incoming("102", TEST_INBOX, "Re: Cursor renewal: pricing", "We've agreed to 20%. Confirmed.")],
        ]
    )
    monkeypatch.setattr(mail, "_imap_poll", lambda subject: next(replies, []))
    monkeypatch.setattr(mail, "_imap_mark_seen", lambda uids: None)

    neg, _ = engine.start("Cursor", 1400, target_pct=20)
    for _ in range(4):
        await engine.tick(neg["id"])

    final = seeded.get(E.NEGOTIATION, neg["id"])
    assert final["status"] == "closed_won" and final["current_offer_pct"] == 20
    assert final["seen_refs"] == ["101", "102"]
    recipients = {r for call in live for r in call["Destination"]["ToAddresses"]}
    assert recipients == {TEST_INBOX}
    assert len(live) == 3  # opening, counter, acceptance
