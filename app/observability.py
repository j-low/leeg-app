"""
Observability setup: OpenTelemetry distributed tracing, Prometheus metrics,
and structlog JSON configuration.

Usage:
  Call configure_observability(settings.otel_endpoint) once at app startup
  (in create_app()). After that, use module-level metric singletons directly
  and get_tracer() for span creation.

  from app.observability import PIPELINE_DURATION, STAGE_DURATION, get_tracer

Prometheus metrics are exposed via a mounted ASGI app at /metrics (see main.py).
OTel spans are exported via OTLP gRPC to the configured endpoint (otel-collector
in production; no-op if endpoint is empty, e.g. in dev/test).
"""
import logging

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

log = logging.getLogger(__name__)

# ── Prometheus metrics (module-level singletons) ──────────────────────────────
# Initialised at import time. Prometheus requires unique metric names across
# the process; these are safe to create once and use anywhere.

PIPELINE_DURATION: Histogram = Histogram(
    "pipeline_duration_seconds",
    "End-to-end pipeline wall-clock latency in seconds",
    ["channel"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

STAGE_DURATION: Histogram = Histogram(
    "pipeline_stage_duration_seconds",
    "Per-stage pipeline latency in seconds",
    ["stage"],
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

PIPELINE_ERRORS: Counter = Counter(
    "pipeline_errors_total",
    "Pipeline errors by stage",
    ["stage"],
)

LLM_TOKENS: Counter = Counter(
    "llm_tokens_total",
    "LLM tokens consumed, split by type",
    ["type"],  # "prompt" | "completion"
)


# ── Setup functions ───────────────────────────────────────────────────────────

def configure_observability(otlp_endpoint: str = "") -> None:
    """Initialise structlog JSON formatting and OTel TracerProvider.

    Call once at application startup before any request handling begins.

    Args:
        otlp_endpoint: OTLP gRPC endpoint for span export, e.g.
                       "http://otel-collector:4317". Pass "" to disable
                       span export (useful in development and tests).
    """
    # ── structlog: JSON format, ISO timestamps, stdout ────────────────────────
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # ── OpenTelemetry TracerProvider ──────────────────────────────────────────
    resource = Resource.create({"service.name": "leeg-api", "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info("OTel OTLP exporter configured: %s", otlp_endpoint)
        except Exception as exc:
            log.warning("OTel exporter setup failed (no-op): %s", exc)

    trace.set_tracer_provider(provider)
    log.info("Observability configured (otlp_endpoint=%r)", otlp_endpoint or "disabled")


def get_tracer() -> trace.Tracer:
    """Return the module tracer. Safe to call before configure_observability()
    — returns a no-op tracer until a provider is set."""
    return trace.get_tracer("leeg.pipeline")


def get_metrics_app():
    """Return the Prometheus ASGI app for mounting at /metrics."""
    return make_asgi_app()
