import pytest

from runway import seed
from runway.config import get_settings
from runway.store import LocalStore, set_store


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """Every test gets a fresh local store, console messaging, demo mail and no LLM."""
    monkeypatch.setenv("RUNWAY_STORE", "local")
    monkeypatch.setenv("RUNWAY_LOCAL_STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("RUNWAY_LLM", "off")
    monkeypatch.setenv("RUNWAY_NOTIFIER", "console")
    monkeypatch.setenv("RUNWAY_MAIL", "demo")
    monkeypatch.setenv("RUNWAY_API_TOKEN", "")
    monkeypatch.setenv("RUNWAY_FOUNDER_PHONE", "")
    get_settings.cache_clear()
    store = LocalStore(tmp_path / "store.json", get_settings().company_id)
    set_store(store)
    yield store
    set_store(None)
    get_settings.cache_clear()


@pytest.fixture
def seeded(env):
    seed.load()
    return env
