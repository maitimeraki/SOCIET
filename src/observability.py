"""Observability: Prometheus metrics, OpenTelemetry tracing, Sentry (plan §10).

Every integration here is env-gated and lazy. Importing this module performs no
network I/O and never fails when nothing is configured — the unconfigured state
is a no-op, because the OTLP collector and Sentry DSN are the operator's to
provision (R10); this code only turns them on when the environment names them.

Telemetry must never break a business path: each integration's own failure is
logged and swallowed here, never raised into a request or a job. Business errors
are never swallowed — only telemetry's.
"""

import logging
import os
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# --- App metrics -------------------------------------------------------------
# Module-level so the API's /metrics and the worker's scrape server both expose
# the same series from the process's default registry. Defining a metric makes
# no network call; increments are cheap in-process counters, so they are always
# recorded even when the scrape endpoint is disabled.

LLM_CALLS = Counter(
    "societas_llm_calls_total",
    "LLM calls issued by the debate batch runner.",
)
LLM_FAILURES = Counter(
    "societas_llm_failures_total",
    "LLM calls that raised, by the debate batch runner.",
)
JOB_DURATION = Histogram(
    "societas_job_duration_seconds",
    "Wall-clock duration of a background job, by kind and terminal status.",
    labelnames=("kind", "status"),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
QUEUE_DEPTH = Gauge(
    "societas_queue_depth",
    "Jobs waiting in the RQ queue (read at scrape time).",
)
QUEUE_FAILED = Gauge(
    "societas_queue_failed",
    "Jobs in the RQ failed registry (read at scrape time).",
)

#: One instrumented app per process — the default registry cannot hold the
#: instrumentator's collectors twice (a second ``instrument`` call raises).
_instrumented = False


def _queue_len() -> float:
    try:
        from src.jobs.queue import get_queue

        return float(len(get_queue()))
    except Exception as exc:  # Redis down, or no queue configured
        logger.warning("queue depth unavailable: %s", exc)
        return 0.0


def _failed_len() -> float:
    try:
        from rq.registry import FailedJobRegistry

        from src.jobs.queue import get_queue

        return float(FailedJobRegistry(queue=get_queue()).count)
    except Exception as exc:
        logger.warning("failed queue count unavailable: %s", exc)
        return 0.0


def _register_queue_gauges() -> None:
    """Read the RQ queue depth at scrape time, not on a background timer."""
    QUEUE_DEPTH.set_function(_queue_len)
    QUEUE_FAILED.set_function(_failed_len)


def setup_metrics(app: Any) -> None:
    """Expose ``/metrics`` and the app metrics on ``app`` when enabled.

    No-op unless ``metrics_enabled`` — the default locally; compose sets it.
    """
    global _instrumented
    if not get_settings().metrics_enabled or _instrumented:
        return
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        _register_queue_gauges()
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        _instrumented = True
        logger.info("Prometheus /metrics enabled")
    except Exception as exc:
        logger.error("metrics setup failed; serving without /metrics: %s", exc)


def setup_worker_metrics() -> None:
    """Serve the worker's registry over HTTP when enabled (RQ workers have no
    FastAPI app, so the instrumentator does not apply)."""
    if not get_settings().metrics_enabled:
        return
    try:
        from prometheus_client import start_http_server

        _register_queue_gauges()
        port = get_settings().metrics_port
        start_http_server(port)
        logger.info("worker metrics served on :%d/metrics", port)
    except Exception as exc:
        logger.error("worker metrics setup failed: %s", exc)


def init_tracing(app: Any) -> None:
    """Auto-instrument the app when an OTLP endpoint is configured.

    Unset ``OTEL_EXPORTER_OTLP_ENDPOINT`` is a zero-op: nothing is imported and
    no exporter is built, so a box without the collector boots untouched.
    """
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": os.environ.get("OTEL_SERVICE_NAME", "societas-api")}
            )
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        PsycopgInstrumentor().instrument()
        RedisInstrumentor().instrument()
        logger.info("OpenTelemetry tracing enabled")
    except Exception as exc:
        logger.error("OpenTelemetry init failed; continuing untraced: %s", exc)


def init_sentry() -> None:
    """Report errors to Sentry when a DSN is configured; otherwise a no-op."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, release=os.environ.get("GIT_SHA", "dev"))
        logger.info("Sentry error reporting enabled")
    except Exception as exc:
        logger.error("Sentry init failed; continuing without it: %s", exc)
