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
    global _initialized, _page_visits, _tracer
    if _initialized:
        return
    _initialized = True

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggingHandler

        resource = Resource({SERVICE_NAME: SERVICE, "host.name": HOSTNAME})
        otlp_endpoint = os.getenv("OTLP_ENDPOINT", "")

        if otlp_endpoint:
            tp = TracerProvider(resource=resource)
            tp.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
            )
            trace.set_tracer_provider(tp)

            mp = MeterProvider(
                resource=resource,
                metric_readers=[
                    PeriodicExportingMetricReader(
                        OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
                    )
                ],
            )
            metrics.set_meter_provider(mp)

            lp = LoggerProvider(resource=resource)
            lp.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs"))
            )
            set_logger_provider(lp)
            handler = LoggingHandler(level=logging.INFO, logger_provider=lp)
            logging.getLogger("page").addHandler(handler)

        meter = metrics.get_meter(SERVICE)
        _page_visits = meter.create_counter(
            name="page_visits_total",
            description="Total page visits",
            unit="1",
        )
        _tracer = trace.get_tracer(SERVICE)

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
        "event": "Request",
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
        "request_body": {},
        "query_params": dict(request.GET),
    }
    _page_logger.info(json.dumps(payload))


def log_response(request, transaction_id, endpoint, status, duration, trace_id=None, span_id=None):
    user = getattr(request, "user", None)
    level = "INFO" if status < 400 else "ERROR"
    payload = {
        "event": "Response",
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
        "response_body": getattr(request, "otel_page_summary", {}),
    }
    if trace_id:
        payload["trace_id"] = trace_id
    if span_id:
        payload["span_id"] = span_id
    _page_logger.info(json.dumps(payload))
