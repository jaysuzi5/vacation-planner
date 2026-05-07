import os
import json
import logging
import socket
from datetime import datetime, timezone

SERVICE = os.getenv("OTEL_SERVICE_NAME", "vacation-planner")
VERSION = "v1"
HOSTNAME = socket.gethostname()

_initialized = False
_page_visits = None
_tracer = None

_page_logger = logging.getLogger("page")

_SKIP_PREFIXES = ("/admin/", "/accounts/", "/static/", "/favicon")


def setup_otel():
    """
    Use providers already initialised by opentelemetry-instrument CLI.
    We only add the 'page' LoggingHandler on top — no provider overrides.
    """
    global _initialized, _page_visits, _tracer
    if _initialized:
        return
    _initialized = True

    try:
        from opentelemetry import trace, metrics

        _tracer = trace.get_tracer(SERVICE)

        meter = metrics.get_meter(SERVICE)
        _page_visits = meter.create_counter(
            name="page_visits_total",
            description="Total page visits",
            unit="1",
        )

        # Wire the 'page' Python logger → OTEL LoggerProvider → OTLP exporter.
        # The existing provider may be a NoOp if OTEL_LOGS_EXPORTER is not set;
        # in that case we fall back to the HTTP log exporter via OTLP_ENDPOINT.
        otlp_endpoint = os.getenv("OTLP_ENDPOINT", "")
        try:
            from opentelemetry._logs import get_logger_provider
            from opentelemetry.sdk._logs import LoggingHandler, LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME
            from opentelemetry._logs import set_logger_provider

            lp = get_logger_provider()
            # If the auto-instrumented provider is a real SDK provider it will
            # have add_log_record_processor; NoOp providers do not.
            if otlp_endpoint and not hasattr(lp, "add_log_record_processor"):
                resource = Resource({SERVICE_NAME: SERVICE, "host.name": HOSTNAME})
                lp = LoggerProvider(resource=resource)
                lp.add_log_record_processor(
                    BatchLogRecordProcessor(
                        OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")
                    )
                )
                set_logger_provider(lp)

            handler = LoggingHandler(level=logging.INFO, logger_provider=lp)
            logging.getLogger("page").addHandler(handler)
        except Exception:
            _page_logger.warning("OTEL log handler setup failed; page logs go to console only")

    except ImportError:
        _page_logger.warning("opentelemetry packages not installed; traces and metrics disabled")


def _remote_addr(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def _endpoint_from_path(path):
    from django.urls import resolve, Resolver404
    try:
        rm = resolve(path)
        url_name = rm.url_name or ""
        return f"planner/{url_name}" if url_name else "planner/unknown"
    except Resolver404:
        parts = [p for p in path.strip("/").split("/") if p]
        return "/".join(parts[:2]) if parts else "planner/home"


def log_request(request, transaction_id, endpoint):
    user = getattr(request, "user", None)
    payload = {
        "event": "page_request",
        "method": request.method,
        "version": VERSION,
        "service": SERVICE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transaction_id": transaction_id,
        "level": "INFO",
        "endpoint": endpoint,
        "hostname": HOSTNAME,
        "path": request.path,
        "remote_addr": _remote_addr(request),
        "user": user.email if user and user.is_authenticated else "anonymous",
        "query_params": dict(request.GET),
    }
    _page_logger.info(json.dumps(payload))


def log_response(request, transaction_id, endpoint, status, duration, trace_id=None, span_id=None):
    user = getattr(request, "user", None)
    level = "INFO" if status < 400 else "ERROR"
    payload = {
        "event": "page_response",
        "method": request.method,
        "version": VERSION,
        "service": SERVICE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transaction_id": transaction_id,
        "level": level,
        "endpoint": endpoint,
        "hostname": HOSTNAME,
        "path": request.path,
        "duration_seconds": round(duration, 6),
        "status": status,
        "user": user.email if user and user.is_authenticated else "anonymous",
    }
    if trace_id:
        payload["trace_id"] = trace_id
    if span_id:
        payload["span_id"] = span_id
    _page_logger.info(json.dumps(payload))
