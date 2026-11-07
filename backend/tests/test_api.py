from fastapi.testclient import TestClient

from runway.api import app
from runway.config import get_settings


def test_health_and_reads(seeded):
    c = TestClient(app)
    assert c.get("/health").json()["ok"]
    m = c.get("/dashboard/metrics").json()
    assert m["ghostSeats"] > 0 and m["activeSubscriptions"] == 15
    trend = c.get("/dashboard/spend-trend").json()
    assert len(trend["labels"]) == len(trend["datasets"]["total"])
    seats = c.get("/seats").json()
    assert any(s["employees"] for s in seats)


def test_token_required_when_configured(seeded, monkeypatch):
    monkeypatch.setenv("RUNWAY_API_TOKEN", "s3cret")
    get_settings.cache_clear()
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.post("/imessage/inbound", json={"sender": "", "text": "y"}).status_code == 401
    ok = c.post("/imessage/inbound", json={"sender": "", "text": "help"}, headers={"X-Runway-Token": "s3cret"})
    assert ok.status_code == 200


def test_transaction_webhook(seeded):
    r = TestClient(app).post("/transactions", json={"merchant": "Anthropic", "amount": 4800})
    assert r.status_code == 200 and r.json()["alert"]["pillar"] == "ai_spend"
