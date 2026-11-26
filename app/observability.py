"""Privacy-conscious JSON request logs for platform log collectors."""
from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

from starlette.requests import Request


logger = logging.getLogger("sawa.http")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


async def request_observability(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid4().hex
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        event = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        logger.info(json.dumps(event, separators=(",", ":"), ensure_ascii=False))
