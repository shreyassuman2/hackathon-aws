"""Long-running worker: advances negotiations and flushes held alerts on an interval.

    uv run python -m runway.negotiation.worker            # run forever
    uv run python -m runway.negotiation.worker --once     # one pass (what the scheduled Lambda does)

Demo trick: kill it with kill -9 mid-negotiation, start it again, and it picks up exactly where
it left off, because all state lives in the store (see engine.py).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from runway import alerts
from runway.config import get_settings
from runway.negotiation import engine

log = logging.getLogger("runway.worker")


async def run_once() -> int:
    n = await engine.tick_all()
    await alerts.flush_held()
    return n


async def run_forever(interval: int) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker up: polling every %ss", interval)
    while not stop.is_set():
        try:
            n = await run_once()
            if n:
                log.info("advanced %d negotiation(s)", n)
        except Exception:
            log.exception("worker pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    log.info("worker stopped cleanly")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=get_settings().negotiation_poll_seconds)
    args = p.parse_args()
    if args.once:
        print(f"advanced {asyncio.run(run_once())} negotiation(s)")
    else:
        asyncio.run(run_forever(args.interval))


if __name__ == "__main__":
    main()
