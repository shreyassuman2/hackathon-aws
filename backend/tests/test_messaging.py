import httpx
import pytest

from runway import messaging
from runway.config import get_settings


@pytest.fixture
def bridge(monkeypatch):
    """Route the API's calls to the iMessage bridge into a fake that records the request."""
    seen: list[httpx.Request] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status["code"], json={"ok": status["code"] == 200})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("RUNWAY_NOTIFIER", "imessage")
    monkeypatch.setenv("RUNWAY_IMESSAGE_BRIDGE_URL", "http://bridge.test")
    get_settings.cache_clear()
    return seen, status


async def test_bridge_send_carries_api_token(env, bridge, monkeypatch):
    seen, _ = bridge
    monkeypatch.setenv("RUNWAY_API_TOKEN", "t" * 24)
    get_settings.cache_clear()
    assert await messaging.send("+14155550100", "hi")
    assert seen[0].url.path == "/send" and seen[0].headers["x-runway-token"] == "t" * 24


async def test_bridge_send_without_token_sends_no_header(env, bridge):
    seen, _ = bridge
    assert await messaging.send("+14155550100", "hi")
    assert "x-runway-token" not in seen[0].headers


async def test_bridge_refusal_is_a_failed_send(env, bridge):
    _, status = bridge
    status["code"] = 401
    assert not await messaging.send("+14155550100", "hi")
