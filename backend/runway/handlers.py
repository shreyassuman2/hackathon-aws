"""AWS Lambda entry points (wired up in infra/template.yaml).

api_handler          HTTP API → FastAPI (via Mangum)
negotiation_handler  EventBridge schedule (every 5 min): advance negotiations + flush held alerts
digest_handler       EventBridge schedule (Mon/Fri mornings): send the digest
"""

from __future__ import annotations

import asyncio
from typing import Any

from mangum import Mangum

from runway.api import app

api_handler = Mangum(app, lifespan="off")


def negotiation_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    from runway.negotiation.worker import run_once

    return {"advanced": asyncio.run(run_once())}


def digest_handler(event: dict[str, Any], context: Any) -> dict[str, bool]:
    from runway import digest

    kind = (event or {}).get("kind", "weekly")
    return {"sent": asyncio.run(digest.send(kind))}
