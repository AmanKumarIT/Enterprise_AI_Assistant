"""
Middleware for structured logging, request tracing,
and Prometheus metrics collection.
"""
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("eka.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured access logging with request ID tracing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        request.state.request_id = request_id

        response = await call_next(request)

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Collects HTTP request metrics for Prometheus."""

    def __init__(self, app):
        super().__init__(app)
        self.request_count = {}
        self.request_latency = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        elapsed = time.time() - start_time

        path = request.url.path
        method = request.method
        status = response.status_code

        key = f"{method}_{path}_{status}"
        self.request_count[key] = self.request_count.get(key, 0) + 1

        if key not in self.request_latency:
            self.request_latency[key] = []
        self.request_latency[key].append(elapsed)

        return response

    def get_metrics(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for key, count in self.request_count.items():
            parts = key.split("_", 2)
            method = parts[0] if len(parts) > 0 else "UNKNOWN"
            rest = "_".join(parts[1:]) if len(parts) > 1 else ""
            lines.append(f'http_requests_total{{endpoint="{key}"}} {count}')

        lines.append("# HELP http_request_duration_seconds HTTP request latency")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for key, latencies in self.request_latency.items():
            avg = sum(latencies) / len(latencies) if latencies else 0
            lines.append(f'http_request_duration_seconds_avg{{endpoint="{key}"}} {avg:.4f}')
            lines.append(f'http_request_duration_seconds_count{{endpoint="{key}"}} {len(latencies)}')

        return "\n".join(lines) + "\n"
