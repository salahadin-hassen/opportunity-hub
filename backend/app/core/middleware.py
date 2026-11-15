"""Observability, request correlation, and security middleware."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("app.access")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach correlation IDs, measure response latency, and log requests.
    
    Extracts an incoming `X-Request-ID` or assigns a new UUIDv4, guarantees
    the header is sent in the response, and logs duration and status code.
    Logs contain NO secrets, passwords, or personal data.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        request.state.request_id = request_id
        start_time = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Request failed: %s %s (request_id=%s, duration=%.2fms)",
                request.method,
                request.url.path,
                request_id,
                duration_ms,
                exc_info=True,
            )
            raise

        duration_ms = (time.monotonic() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id

        # Skip spamming access logs on health check polls
        if request.url.path != "/health":
            logger.info(
                "%s %s %d (request_id=%s, duration=%.2fms)",
                request.method,
                request.url.path,
                response.status_code,
                request_id,
                duration_ms,
            )

        return response

