"""Load the Acme Labs demo dataset.

    uv run python -m runway.seed            # load (keeps existing data)
    uv run python -m runway.seed --reset    # wipe local store first

Dates are shifted so the newest transaction lands yesterday. That keeps "last 30 days",
"renews in 7 days" and the spike detector meaningful no matter when you run the demo.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from runway import entities as E
from runway.store import LocalStore, get_store

SEED_FILE = Path(__file__).parent / "seed" / "demo.json"


def _shift(value: Any, delta: timedelta) -> Any:
    if not isinstance(value, str) or len(value) < 10 or value[4] != "-" or value[7] != "-":
        return value
    try:
        if len(value) == 10:
            return (date.fromisoformat(value) + delta).isoformat()
        return (datetime.fromisoformat(value) + delta).isoformat()
    except ValueError:
        return value


def load(reset: bool = False) -> dict[str, int]:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))["entities"]  # Windows defaults to cp1252
    # Anchor on the newest event of any kind (alerts are stamped after their transactions).
    newest = max(datetime.fromisoformat(r["created_at"]) for ent in (E.TRANSACTION, E.ALERT) for r in data[ent])
    delta = timedelta(days=(datetime.now(UTC) - newest).days - 1)

    store = get_store()
    if reset and isinstance(store, LocalStore):
        store.reset()
    counts = {}
    for entity, rows in data.items():
        shifted = [{k: _shift(v, delta) for k, v in r.items()} for r in rows]
        counts[entity] = store.put_many(entity, shifted)  # type: ignore[attr-defined]
    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="wipe the local store first")
    counts = load(reset=p.parse_args().reset)
    print("seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
