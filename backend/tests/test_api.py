import pytest
from fastapi.testclient import TestClient

from runway import entities as E
from runway import handlers
from runway.api import app
from runway.config import get_settings


@pytest.fixture
def client(seeded):
    return TestClient(app)


def test_health_is_open(client, monkeypatch):
    monkeypatch.setenv("RUNWAY_API_TOKEN", "x" * 24)
    get_settings.cache_clear()
    assert client.get("/health").json()["ok"] is True


def test_token_required_when_set(client, monkeypatch):
    monkeypatch.setenv("RUNWAY_API_TOKEN", "s3cret-token-0123456789")
    get_settings.cache_clear()
    assert client.get("/alerts").status_code == 401
    assert client.get("/alerts", headers={"X-Runway-Token": "wrong"}).status_code == 401
    assert client.get("/alerts", headers={"X-Runway-Token": "s3cret-token-0123456789"}).status_code == 200


def test_transaction_returns_alert(client):
    r = client.post("/transactions", json={"merchant": "Anthropic", "amount": 4800})
    assert r.status_code == 200
    alert = r.json()["alert"]
    assert alert["pillar"] == "ai_spend" and alert["message"]


def test_inbound_command_and_decision(client):
    r = client.post("/imessage/inbound", json={"text": "show pending"})
    assert r.json()["reply"].startswith("Waiting on you")
    pending = client.get("/alerts", params={"pending": True}).json()
    alert_id = pending[0]["id"]
    d = client.post(f"/alerts/{alert_id}/decision", json={"accept": False})
    assert d.json()["alert"]["resolved"] is True
    assert client.post(f"/alerts/{alert_id}/decision", json={"accept": True}).status_code == 409


def test_negotiation_lifecycle(client, seeded):
    r = client.post("/negotiations", json={"vendor": "Cursor", "price": 1400, "target_pct": 20, "demo": True})
    neg = r.json()["negotiation"]
    assert r.json()["created"] and neg["status"] == "waiting"
    for _ in range(4):
        neg = client.post(f"/negotiations/{neg['id']}/tick").json()
    assert neg["status"] == "closed_won"
    assert client.get("/negotiations").json()[0]["id"] == neg["id"]
    assert client.get("/negotiations/nope").status_code == 404


def test_dashboard_metrics(client):
    m = client.get("/dashboard/metrics").json()
    assert m["spend_total"] > 0 and m["pending_alerts"] > 0 and "spend_by_pillar" in m


def test_policy_patch(client, seeded):
    r = client.patch("/policies/policy-auto-cancel", json={"threshold_amount": 150})
    assert r.json()["threshold_amount"] == 150
    assert seeded.get(E.POLICY, "policy-auto-cancel")["threshold_amount"] == 150


def test_lambda_handlers(seeded):
    assert handlers.digest_handler({"kind": "morning"})["text"].startswith("☀️ Monday brief")
    assert handlers.negotiation_handler({}, None) == {"advanced": 0}


def test_dashboard_routes_for_frontend(client):
    """The routes and metric keys frontend/lib/api.js reads."""
    m = client.get("/dashboard/metrics").json()
    for key in ("totalMonthlySpend", "identifiedSavings", "ghostSeats", "complianceFlags", "activeSubscriptions"):
        assert isinstance(m[key], int), key
    assert m["ghostSeats"] > 0 and m["activeSubscriptions"] > 0

    trend = client.get("/dashboard/spend-trend").json()
    assert len(trend["labels"]) == 7 and set(trend["datasets"]) == {"total", "ai", "saas", "expenses"}
    assert sum(trend["datasets"]["total"]) > 0
    assert client.get("/dashboard/spend-trend", params={"bucket_days": 0}).status_code == 422

    subs = client.get("/subscriptions").json()
    assert subs and subs == sorted(subs, key=lambda r: r["renewal_date"])
    assert client.get("/seats").json()[0]["tool"]
    assert client.get("/ai-usage").json()[0]["week_start"]
    emps = client.get("/employees").json()
    assert emps and set(emps[0]) == {"id", "name", "role", "email"}  # no phone numbers
