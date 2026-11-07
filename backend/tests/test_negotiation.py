from runway import entities as E
from runway.negotiation import engine, mail


async def _run_to_end(max_ticks=10):
    for _ in range(max_ticks):
        await engine.tick_all()


async def test_demo_negotiation_closes_won(seeded):
    neg, created = engine.start("Cursor", 1400, target_pct=20, demo=True)
    assert created
    await _run_to_end()
    n = seeded.get(E.NEGOTIATION, neg["id"])
    assert n["status"] == "closed_won" and n["current_offer_pct"] == 22
    assert all(o["sent"] for o in n["outbox"])
    assert [h for h in seeded.list(E.NEGOTIATION_HISTORY) if h["vendor"] == "Cursor" and h["outcome"] == "won"]
    assert any(s.get("source_id") == neg["id"] for s in seeded.list(E.SAVINGS))


async def test_duplicate_start_reuses_active(seeded):
    a, _ = engine.start("Notion", 480, demo=True)
    b, created = engine.start("notion", 480, demo=True)
    assert not created and a["id"] == b["id"]


async def test_vendor_rejection_closes_lost(seeded):
    neg, _ = engine.start("Notion", 480, demo=True)
    await _run_to_end()
    assert seeded.get(E.NEGOTIATION, neg["id"])["status"] == "closed_lost"


async def test_restart_does_not_replay_replies(seeded):
    """Old bug: after kill -9 the demo inbox restarted at reply #1. Now the cursor is persisted."""
    neg, _ = engine.start("Cursor", 1400, target_pct=20, demo=True)
    await engine.tick(neg["id"])  # opening email
    await engine.tick(neg["id"])  # reply 1 (10%) -> counter
    mid = seeded.get(E.NEGOTIATION, neg["id"])
    assert mid["inbox_cursor"] == 1 and mid["round"] == 2
    # "Restart": nothing in memory survives; state comes only from the store.
    await engine.tick(neg["id"])
    after = seeded.get(E.NEGOTIATION, neg["id"])
    assert after["inbox_cursor"] == 2 and after["current_offer_pct"] == 18


async def test_crash_before_email_send_keeps_it_queued(seeded, monkeypatch):
    neg, _ = engine.start("Cursor", 1400, demo=True)
    monkeypatch.setattr(mail, "send", lambda *a, **k: False)  # SES down / process dies before sending
    await engine.tick(neg["id"])
    n = seeded.get(E.NEGOTIATION, neg["id"])
    assert n["status"] == "waiting" and [o for o in n["outbox"] if not o["sent"]]
    sent = []
    monkeypatch.setattr(mail, "send", lambda to, subject, body, demo: sent.append(subject) or True)
    await engine.tick(neg["id"])
    assert sent[0] == "Cursor renewal: pricing"  # the queued opening email went out exactly once first
    assert sent.count("Cursor renewal: pricing") == 1
