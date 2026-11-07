"""Email in and out for negotiations.

Outbound: Amazon SES (RUNWAY_MAIL=live) or printed to the console (demo).
Inbound:  IMAP polling (live) or canned fixtures (demo).

Inbound is two-phase so a crash can't lose a reply: `poll()` reads without marking anything,
the engine saves state, then `ack()` marks the messages as handled.
"""

from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass
from email.header import decode_header, make_header
from typing import Any

from runway.config import get_settings
from runway.negotiation import fixtures

log = logging.getLogger("runway.mail")


@dataclass
class Incoming:
    ref: str  # IMAP UID, or fixture index in demo mode
    sender: str
    subject: str
    body: str


# ── outbound ──────────────────────────────────────────────────────────────────


def send(to: str, subject: str, body: str, *, demo: bool) -> bool:
    if demo:
        print(f"\n📧 [demo] → {to}\nSubject: {subject}\n\n{body}\n", flush=True)
        return True
    s = get_settings()
    if not s.email_from:
        log.error("RUNWAY_EMAIL_FROM is not set; cannot send live email")
        return False
    # Last line of defence: with an override set, nothing goes anywhere else, even for deals started before it.
    if (override := s.vendor_email_override.strip()) and to != override:
        log.info("redirecting vendor email for %s to %s (RUNWAY_VENDOR_EMAIL_OVERRIDE)", to, override)
        to = override
    import boto3

    try:
        boto3.client("sesv2", region_name=s.aws_region).send_email(
            FromEmailAddress=s.email_from,
            Destination={"ToAddresses": [to]},
            Content={"Simple": {"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}}},
        )
        return True
    except Exception as exc:
        log.warning("SES send to %s failed: %s", to, exc)
        return False


# ── inbound ───────────────────────────────────────────────────────────────────


def poll(state: dict[str, Any]) -> list[Incoming]:
    if state.get("demo"):
        cursor = int(state.get("inbox_cursor") or 0)
        replies = fixtures.replies_for(state["vendor"])
        if cursor >= len(replies):
            return []
        sender, body = replies[cursor]
        return [Incoming(ref=str(cursor), sender=sender, subject=f"Re: {state['subject']}", body=body)]
    return _imap_poll(state["subject"])


def ack(state: dict[str, Any], msgs: list[Incoming]) -> None:
    if state.get("demo") or not msgs:
        return  # demo progress lives in state["inbox_cursor"]
    _imap_mark_seen([m.ref for m in msgs])


def _imap() -> imaplib.IMAP4_SSL | None:
    s = get_settings()
    if not (s.imap_user and s.imap_password):
        log.info("IMAP not configured; skipping inbox poll")
        return None
    conn = imaplib.IMAP4_SSL(s.imap_host, s.imap_port)
    conn.login(s.imap_user, s.imap_password)
    conn.select("INBOX")
    return conn


def _body(msg: email.message.Message) -> str:
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None) if msg.is_multipart() else msg
    payload = part.get_payload(decode=True) if part else None
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace") if payload else ""


def _imap_poll(subject: str) -> list[Incoming]:
    conn = None
    try:
        conn = _imap()
        if conn is None:
            return []
        safe = subject.replace('"', "")
        _, data = conn.uid("search", None, f'(UNSEEN SUBJECT "{safe}")')
        out = []
        for uid in (data[0] or b"").split():
            _, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")  # PEEK: don't mark as read yet
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            out.append(
                Incoming(
                    ref=uid.decode(),
                    sender=msg.get("From", ""),
                    subject=str(make_header(decode_header(msg.get("Subject", "")))),
                    body=_body(msg),
                )
            )
        return out
    except Exception as exc:
        log.warning("IMAP poll failed: %s", exc)
        return []
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass


def _imap_mark_seen(uids: list[str]) -> None:
    conn = None
    try:
        conn = _imap()
        if conn:
            for uid in uids:
                conn.uid("store", uid, "+FLAGS", "(\\Seen)")
    except Exception as exc:
        log.warning("IMAP ack failed (replies may be re-read; engine dedupes): %s", exc)
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass
