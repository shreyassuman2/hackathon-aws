"""The negotiation state machine.

One NEGOTIATION record per deal. `tick(id)` advances a deal by one step and is safe to call
from anywhere, any number of times (a local loop, a scheduled Lambda, an API call):

    opening ──(round-1 email queued)──▶ waiting ──reply──▶ classify ─▶ decide
                                          ▲                              │
                                          └──── counter email queued ◀──┤
                                                                         ├─▶ closed_won
                                                                         ├─▶ closed_lost
                                                                         └─▶ needs_founder ─(Y/N)─▶ won/lost

Crash safety:
  * Every state change is ONE optimistic-locked write (`expect_version`). If two workers race,
    one gets ConflictError and simply retries next tick.
  * Side effects (emails, texts) are queued in `outbox` in that same write, then flushed.
    Kill the process at any point: on restart the state is consistent and unsent mail is still queued.
  * Demo replies are read by `inbox_cursor`, which is saved with the state, so a restart never replays them.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from runway import entities as E
from runway import messaging, policies
from runway.config import get_settings
from runway.models import Finding
from runway.negotiation import mail, reasoner
from runway.store import ConflictError, Record, find, find_one, get_store, new_id

log = logging.getLogger("runway.negotiation")

ACTIVE = {"opening", "waiting", "needs_founder"}
CLOSED = {"closed_won", "closed_lost", "stalled", "cancelled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _signoff() -> str:
    name = get_settings().founder_name
    return "the team" if name == "the founder" else name


def active_for(vendor: str) -> Record | None:
    return find_one(
        get_store(),
        E.NEGOTIATION,
        lambda n: n.get("status") in ACTIVE and policies.same_vendor(n.get("vendor", ""), vendor),
    )


def list_negotiations(limit: int = 50) -> list[Record]:
    return find(get_store(), E.NEGOTIATION, order_by="updated_at", desc=True, limit=limit)


# ── lifecycle ─────────────────────────────────────────────────────────────────


def _recipient(vendor: str, vendor_email: str | None, demo: bool) -> tuple[str, bool, str]:
    """Who the vendor emails go to: (address, demo, note for the log).

    Live mode never emails a guessed address like renewals@cursor.com, which is a real company.
    It needs either RUNWAY_VENDOR_EMAIL_OVERRIDE (a test inbox) or an explicit vendor_email.
    """
    override = get_settings().vendor_email_override.strip()
    if override:
        return override, demo, f"vendor emails redirected to {override} (RUNWAY_VENDOR_EMAIL_OVERRIDE)"
    if vendor_email:
        return vendor_email, demo, ""
    guessed = f"renewals@{vendor.lower().replace(' ', '')}.com"
    if demo:
        return guessed, True, ""
    log.warning("live mail but no vendor email for %s; running in demo mode instead of emailing %s", vendor, guessed)
    return guessed, True, f"no vendor email and no RUNWAY_VENDOR_EMAIL_OVERRIDE: demo mode, NOT emailing {guessed}"


def start(
    vendor: str,
    price: float,
    *,
    target_pct: float | None = None,
    vendor_email: str | None = None,
    demo: bool | None = None,
    alert_id: str | None = None,
) -> tuple[Record, bool]:
    """Create a negotiation. Returns (record, created). An active deal for the vendor is reused."""
    if existing := active_for(vendor):
        return existing, False
    s = get_settings()
    demo = s.mail == "demo" if demo is None else demo
    to, demo, why = _recipient(vendor, vendor_email, demo)
    wins = find(
        get_store(),
        E.NEGOTIATION_HISTORY,
        lambda h: h.get("outcome") == "won",
        order_by="initiated_date",
        desc=True,
        limit=3,
    )
    rec = get_store().put(
        E.NEGOTIATION,
        {
            "vendor": vendor,
            "vendor_email": to,
            "original_price": float(price),
            "target_pct": float(target_pct or s.negotiation_default_target_pct),
            "floor_pct": s.negotiation_floor_pct,
            "subject": f"{vendor} renewal: pricing",
            "status": "opening",
            "round": 0,
            "current_offer_pct": None,
            "thread": [],
            "leverage_used": [],
            "log": [f"{_now()} created (target {target_pct or s.negotiation_default_target_pct:g}%)"]
            + ([f"{_now()} {why}"] if why else []),
            "outbox": [],
            "inbox_cursor": 0,
            "seen_refs": [],
            "demo": s.mail == "demo" if demo is None else demo,
            "alert_id": alert_id,
            "reference_wins": [w.get("thread_summary") for w in wins],
            "last_activity_at": _now(),
        },
    )
    return rec, True


def _queue_email(st: dict[str, Any], body: str, *, reply: bool) -> None:
    subject = f"Re: {st['subject']}" if reply else st["subject"]
    st["outbox"].append(
        {"id": new_id(), "kind": "email", "to": st["vendor_email"], "subject": subject, "body": body, "sent": False}
    )
    st["thread"].append({"direction": "out", "body": body, "at": _now(), "round": st["round"]})


def _queue_text(st: dict[str, Any], text: str) -> None:
    st["outbox"].append({"id": new_id(), "kind": "founder", "body": text, "sent": False})


def _queue_record(st: dict[str, Any], entity: str, record: dict[str, Any]) -> None:
    """Writes to other entities also go through the outbox, so they happen exactly when the state commits."""
    st["outbox"].append({"id": new_id(), "kind": "record", "entity": entity, "record": record, "sent": False})


def _close(st: dict[str, Any], status: str, notes: str) -> None:
    st["status"] = status
    st["closed_at"] = _now()
    st["outcome_notes"] = notes
    _queue_record(
        st,
        E.NEGOTIATION_HISTORY,
        {
            "vendor": st["vendor"],
            "initiated_date": st.get("created_at"),
            "original_price": st["original_price"],
            "target_discount": st["target_pct"],
            "outcome": "won" if status == "closed_won" else "lost",
            "thread_summary": notes,
        },
    )


def _win(st: dict[str, Any], pct: float) -> None:
    price = float(st["original_price"])
    saved = price * pct / 100
    _queue_email(st, reasoner.draft_acceptance(st, pct, _signoff()), reply=True)
    _close(st, "closed_won", f"Won {pct:g}% off. ${price - saved:,.0f}/mo (was ${price:,.0f}).")
    st["current_offer_pct"] = pct
    st["savings_monthly"] = saved
    _queue_text(
        st,
        f"✅ Closed {st['vendor']} at {pct:g}% off: ${price - saved:,.0f}/mo, down from "
        f"${price:,.0f}. That's ${saved * 12:,.0f}/yr saved, in {st['round']} round(s).",
    )
    _queue_record(
        st,
        E.SAVINGS,
        {
            "title": f"{st['vendor']} renewal negotiated",
            "amount_monthly": saved,
            "status": "realized",
            "source_type": "negotiation",
            "source_id": st["id"],
        },
    )


async def _step(st: dict[str, Any], handled: list[mail.Incoming]) -> bool:
    """Mutate `st` in place for one step. Appends processed replies to `handled`. True if anything changed."""
    s = get_settings()

    if st["status"] == "opening":
        lev = reasoner.pick_leverage(st["leverage_used"])
        st["round"] = 1
        _queue_email(st, await reasoner.draft_opening(st, lev, _signoff()), reply=False)
        st["leverage_used"] += lev
        st["status"] = "waiting"
        st["last_activity_at"] = _now()
        _queue_text(
            st,
            f"📧 Sent {st['vendor']} our ask: {st['target_pct']:g}% off. I'll handle the back-and-forth "
            f"and text you when it's done.",
        )
        return True

    if st["status"] != "waiting":
        return False

    incoming = [m for m in mail.poll(st) if m.ref not in st["seen_refs"]]
    if not incoming:
        idle = datetime.now(UTC) - datetime.fromisoformat(st["last_activity_at"])
        if idle > timedelta(days=s.negotiation_stall_days):
            _close(st, "stalled", f"No reply in {s.negotiation_stall_days} days.")
            _queue_text(
                st,
                f"⏸ {st['vendor']} hasn't replied in {s.negotiation_stall_days} days. "
                f"Want me to nudge them, or cancel instead?",
            )
            return True
        return False

    for msg in incoming:
        handled.append(msg)
        st["seen_refs"].append(msg.ref)
        if st.get("demo"):
            st["inbox_cursor"] = int(st.get("inbox_cursor") or 0) + 1
        st["thread"].append({"direction": "in", "body": msg.body, "at": _now(), "round": st["round"]})
        st["last_activity_at"] = _now()

        c = await reasoner.classify(msg.body, st)
        if c.offer_pct is not None:
            st["current_offer_pct"] = c.offer_pct
        move = reasoner.decide(
            st,
            c,
            max_rounds=s.negotiation_max_rounds,
            policy_allows_accept=c.offer_pct is not None
            and policies.auto_accept_discount(st["vendor"], float(st["original_price"]), c.offer_pct),
        )
        st["log"].append(f"{_now()} round {st['round']}: {c.kind} {c.offer_pct}% → {move.action} ({move.reason})")

        if move.action == "accept":
            _win(st, move.ask_pct if move.ask_pct is not None else float(st["target_pct"]))
            break
        if move.action == "walk_away":
            _close(st, "closed_lost", "Vendor declined any discount.")
            _queue_text(
                st,
                f"❌ {st['vendor']} won't discount after {st['round']} round(s). "
                f"Want me to cut unused seats or cancel instead?",
            )
            break
        if move.action == "ask_founder":
            st["status"] = "needs_founder"
            st["pending_offer_pct"] = c.offer_pct
            st["pending_alert"] = {"offer_pct": c.offer_pct, "reason": move.reason, "below_floor": move.below_floor}
            break
        if move.action == "counter":
            lev = reasoner.pick_leverage(st["leverage_used"], n=1)
            st["round"] += 1
            _queue_email(
                st,
                await reasoner.draft_counter(st, c.offer_pct, move.ask_pct or st["target_pct"], lev, _signoff()),
                reply=True,
            )
            st["leverage_used"] += lev
            _queue_text(
                st, f"🔄 {st['vendor']} offered {c.offer_pct:g}%. Pushing for {move.ask_pct:g}% (round {st['round']})."
            )
        # "wait": nothing to do until the next reply
    return True


async def _flush(rec: Record) -> Record:
    """Deliver queued side effects, marking each one sent with an optimistic write."""
    store = get_store()
    for item in [i for i in rec.get("outbox", []) if not i["sent"]]:
        if item["kind"] == "email":
            ok = mail.send(item["to"], item["subject"], item["body"], demo=bool(rec.get("demo")))
        elif item["kind"] == "record":
            store.put(item["entity"], {"id": item["id"], **item["record"]})  # id = outbox id: idempotent
            ok = True
        else:
            ok = await messaging.send_to_founder(item["body"])
        if not ok:
            break  # keep order; retry on the next tick
        outbox = [{**i, "sent": True} if i["id"] == item["id"] else i for i in rec["outbox"]]
        rec = store.update(E.NEGOTIATION, rec["id"], {"outbox": outbox}, expect_version=rec["version"])
    return rec


async def _raise_founder_alert(rec: Record) -> Record:
    """Turn a `pending_alert` into a real Y/N alert (once)."""
    from runway import alerts  # local import: alerts -> messaging, no cycle with engine at import time

    p = rec.get("pending_alert")
    if not p:
        return rec
    offer = p.get("offer_pct")
    price = float(rec["original_price"])
    msg = (
        (
            f"{rec['vendor']} came back at {offer:g}% off (${price * (1 - offer / 100):,.0f}/mo), short of our "
            f"{rec['target_pct']:g}% target: {p['reason']}."
        )
        if offer is not None
        else f"{rec['vendor']} negotiation needs you: {p['reason']}."
    )
    alert = await alerts.raise_alert(
        Finding(
            pillar="saas_sprawl",
            agent="negotiation",
            alert_type="negotiation_decision",
            message=msg,
            requires_action=True,
            action_prompt=f"Accept {offer:g}%?" if offer is not None else "Keep negotiating?",
            below_policy_floor=bool(p.get("below_floor")),
            confidence=0.95,
            metadata={"negotiation_id": rec["id"], "vendor": rec["vendor"], "offer_pct": offer},
        )
    )
    return get_store().update(
        E.NEGOTIATION,
        rec["id"],
        {"pending_alert": None, "founder_alert_id": alert["id"]},
        expect_version=rec["version"],
    )


async def tick(neg_id: str) -> Record | None:
    store = get_store()
    rec = store.get(E.NEGOTIATION, neg_id)
    if rec is None:
        return None
    rec = await _flush(rec)  # finish anything a previous (maybe crashed) tick queued
    if rec["status"] in CLOSED:
        return rec

    st = {k: (list(v) if isinstance(v, list) else v) for k, v in rec.items()}
    handled: list[mail.Incoming] = []
    changed = await _step(st, handled)
    if changed:
        try:
            rec = store.update(
                E.NEGOTIATION,
                neg_id,
                {k: v for k, v in st.items() if k not in ("id", "version", "created_at")},
                expect_version=rec["version"],
            )
        except ConflictError:
            log.info("negotiation %s changed concurrently; will retry next tick", neg_id)
            return store.get(E.NEGOTIATION, neg_id)
        mail.ack(rec, handled)  # after the commit; seen_refs also dedupes if this fails
    rec = await _raise_founder_alert(rec)
    return await _flush(rec)


async def tick_all() -> int:
    """Advance every open negotiation once. This is what the worker / scheduled Lambda calls."""
    n = 0
    for rec in find(
        get_store(),
        E.NEGOTIATION,
        lambda r: r.get("status") in ACTIVE or any(not i["sent"] for i in r.get("outbox", [])),
    ):
        try:
            await tick(rec["id"])
            n += 1
        except Exception:
            log.exception("tick failed for negotiation %s", rec["id"])
    return n


async def founder_decision(neg_id: str, accept: bool) -> Record | None:
    """Founder replied Y/N to a needs_founder alert."""
    store = get_store()
    rec = store.get(E.NEGOTIATION, neg_id)
    if not rec or rec["status"] != "needs_founder":
        return rec
    st = {k: (list(v) if isinstance(v, list) else v) for k, v in rec.items()}
    offer = st.get("pending_offer_pct")
    if accept and offer is not None:
        _win(st, float(offer))
    else:
        _close(st, "closed_lost", "Founder declined the vendor's final offer.")
        _queue_text(st, f"OK, walked away from {st['vendor']}'s offer. Want me to look at cancelling or cutting seats?")
    rec = store.update(
        E.NEGOTIATION,
        neg_id,
        {k: v for k, v in st.items() if k not in ("id", "version", "created_at")},
        expect_version=rec["version"],
    )
    return await _flush(rec)


def cancel(neg_id: str) -> Record | None:
    rec = get_store().get(E.NEGOTIATION, neg_id)
    if not rec or rec["status"] in CLOSED:
        return rec
    return get_store().update(
        E.NEGOTIATION, neg_id, {"status": "cancelled", "closed_at": _now(), "outcome_notes": "Stopped by founder."}
    )
