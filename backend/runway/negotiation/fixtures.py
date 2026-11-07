"""Canned vendor replies for demo mode (RUNWAY_MAIL=demo).

The engine reads reply N+1 when the negotiation's `inbox_cursor` is N. The cursor is saved with
the rest of the state, so a killed worker resumes at the right reply instead of replaying them.
"""

from __future__ import annotations

CURSOR = [
    (
        "renewals@cursor.com",
        "Hi there,\n\nThanks for reaching out about your renewal. We can offer a 10% discount on your current "
        "plan if you commit to an annual contract.\n\nLet us know if that works.\n\nBest,\nSarah, Cursor Renewals",
    ),
    (
        "renewals@cursor.com",
        "Hi,\n\nI spoke with my manager and we can go up to 18% off on an annual commitment.\n\n"
        "Would that work for your team?\n\nBest,\nSarah, Cursor Renewals",
    ),
    (
        "renewals@cursor.com",
        "Hi,\n\nAfter internal review, we've agreed to match your ask. We can confirm a 22% discount on a "
        "12-month term.\n\nI'll send the updated contract today.\n\nBest,\nSarah, Cursor Renewals",
    ),
]

NOTION = [
    (
        "billing@makenotion.com",
        "Hi,\n\nThank you for being a Notion customer. Unfortunately, we're unable to offer discounts on the Team "
        "plan. Our pricing is standardized across all customers.\n\nWe'd be happy to help you remove inactive "
        "members instead.\n\nBest,\nNotion Support",
    ),
]

GENERIC = [
    (
        "sales@vendor.example",
        "Hi,\n\nWe can offer 12% off your renewal if you commit to annual billing. Let me know if you'd like to "
        "proceed.\n\nRegards,\nVendor Sales",
    ),
    (
        "sales@vendor.example",
        "Hi,\n\nWe've agreed to your requested discount of 20%. Confirmed and applied to your next billing "
        "cycle.\n\nRegards,\nVendor Sales",
    ),
]


def replies_for(vendor: str) -> list[tuple[str, str]]:
    v = vendor.lower()
    if "cursor" in v:
        return CURSOR
    if "notion" in v:
        return NOTION
    return GENERIC
