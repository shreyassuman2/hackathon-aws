"""AWS Lambda entry points (see infra/template.yaml).

ApiFunction          runway.handlers.api_handler          FastAPI behind an HTTP API, via Mangum
NegotiationFunction  runway.handlers.negotiation_handler  every 5 min: tick all deals, flush held alerts
DigestFunction       runway.handlers.digest_handler       Mon 8am / Fri 4pm PT: {"kind": "morning"|"weekly"}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mangum import Mangum

from runway import digest
from runway.api import app
from runway.negotiation import worker

logging.getLogger().setLevel(logging.INFO)

api_handler = Mangum(app, lifespan="off")


def negotiation_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    return {"advanced": asyncio.run(worker.run_once())}


def digest_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    kind = (event or {}).get("kind", "weekly")
    if kind not in ("morning", "weekly"):
        kind = "weekly"
    return asyncio.run(digest.send(kind))
