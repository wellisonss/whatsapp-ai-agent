"""Middleware de logging."""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request

from ..core.logging import get_logger

log = get_logger(__name__)


async def request_logger(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
    t0 = time.time()
    try:
        resp = await call_next(request)
    finally:
        dur_ms = int((time.time() - t0) * 1000)
        log.info("http.request", method=request.method, path=request.url.path, dur_ms=dur_ms)
        structlog.contextvars.clear_contextvars()
    return resp
