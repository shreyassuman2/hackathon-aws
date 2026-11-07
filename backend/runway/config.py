"""All runtime configuration, read once from the environment (or `.env`).

Every setting has a working local default, so `make dev` runs with zero AWS setup:
  - storage falls back to a local JSON file
  - the LLM falls back to deterministic templates
  - outbound messages print to the console
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_prefix="RUNWAY_", extra="ignore")

    # ── Tenant ────────────────────────────────────────────────────────────────
    company_id: str = "00000001-0000-4000-8000-000000000001"
    founder_phone: str = ""  # E.164, e.g. +15551234567
    founder_name: str = "the founder"
    founder_tz_offset: int = -7  # hours from UTC, used for business-hours gating

    # ── API ───────────────────────────────────────────────────────────────────
    # When set, every route except /health requires header `X-Runway-Token: <value>`.
    # ALWAYS set this when the API is reachable from the internet (it can approve spend).
    api_token: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001"

    # ── Storage ───────────────────────────────────────────────────────────────
    store: Literal["local", "dynamodb"] = "local"
    local_store_path: str = ".data/runway.json"
    dynamodb_table: str = "runway"
    dynamodb_endpoint: str | None = None  # set to http://localhost:8001 for DynamoDB Local

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"

    # ── LLM (Claude on Amazon Bedrock) ────────────────────────────────────────
    llm: Literal["bedrock", "off"] = "off"
    # fast = routing / classification, smart = analysis / drafting / chat
    model_fast: str = "anthropic.claude-haiku-5-5"
    model_smart: str = "anthropic.claude-sonnet-5-5"

    # ── Messaging ─────────────────────────────────────────────────────────────
    notifier: Literal["console", "imessage"] = "console"
    imessage_bridge_url: str = "http://127.0.0.1:3099"

    # ── Email (negotiations) ──────────────────────────────────────────────────
    mail: Literal["demo", "live"] = "demo"
    email_from: str = ""  # SES-verified sender
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""

    # ── Negotiation engine ────────────────────────────────────────────────────
    negotiation_poll_seconds: int = 10
    negotiation_max_rounds: int = 4
    negotiation_floor_pct: float = 5.0
    negotiation_default_target_pct: float = 20.0
    negotiation_stall_days: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
