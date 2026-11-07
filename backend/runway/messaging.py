"""Outbound messages to the founder and employees, plus chat history.

Backends (RUNWAY_NOTIFIER):
  console  - print to stdout (default; anyone on the team can run this)
  imessage - POST to the Node bridge in /bridge (macOS only, see bridge/README.md)

Every outbound message is saved to the MESSAGE entity, so the dashboard and Ask-Anything
can see the conversation.
"""

from __future__ import annotations

import logging
import re

import httpx

from runway import entities as E
from runway.config import get_settings
from runway.store import find, get_store

log = logging.getLogger("runway.messaging")


def normalize_phone(raw: str | None) -> str:
    """'(415) 555-0100' / '14155550100' / '+1 415 555 0100' -> '+14155550100'. Emails pass through."""
    if not raw:
        return ""
    raw = raw.strip()
    if "@" in raw:
        return raw.lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return f"+{digits}" if digits else ""


def founder_phone() -> str:
    return normalize_phone(get_settings().founder_phone)


def is_founder(sender: str) -> bool:
    f = founder_phone()
    return bool(f) and normalize_phone(sender) == f


def _chat_key(chat_id: str) -> str:
    return normalize_phone(chat_id) or chat_id or "founder"


def save_message(chat_id: str, role: str, content: str) -> None:
    try:
        get_store().put(E.MESSAGE, {"chat_id": _chat_key(chat_id), "role": role, "content": content})
    except Exception as exc:
        log.warning("could not save message: %s", exc)


def chat_history(chat_id: str, limit: int = 10) -> list[dict[str, str]]:
    cid = _chat_key(chat_id)
    rows = find(
        get_store(), E.MESSAGE, lambda r: r.get("chat_id") == cid, order_by="created_at", desc=True, limit=limit
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def _deliver(to: str, text: str) -> bool:
    s = get_settings()
    if s.notifier == "console":
        print(f"\n📱 → {to or '(founder phone not set)'}\n{text}\n", flush=True)
        return True
    if not to:
        log.warning("no recipient configured; dropping message")
        return False
    # The bridge checks the same shared token as the API, so a tunnelled bridge can't be used by anyone else.
    headers = {"x-runway-token": s.api_token} if s.api_token else {}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{s.imessage_bridge_url}/send", json={"to": to, "text": text}, headers=headers)
            if r.status_code in (401, 403):
                log.warning("iMessage bridge refused the send (%s): check RUNWAY_API_TOKEN matches", r.status_code)
                return False
            return r.status_code == 200 and bool(r.json().get("ok"))
    except httpx.HTTPError as exc:
        log.warning("iMessage bridge unreachable: %s", exc)
        return False


async def send(to: str, text: str) -> bool:
    to = normalize_phone(to)
    save_message(to, "assistant", text)
    return await _deliver(to, text)


async def send_to_founder(text: str, *, ask: str | None = None) -> bool:
    """Text the founder. If `ask` is given, it's appended as a Y/N question."""
    if ask:
        text = f"{text}\n\n{ask}\nReply Y or N."
    return await send(founder_phone(), text)
