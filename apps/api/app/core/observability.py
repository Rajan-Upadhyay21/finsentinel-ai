from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request
from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS = Counter(
    "finsentinel_http_requests_total",
    "Total FinSentinel HTTP requests.",
    ["method", "route", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "finsentinel_http_request_duration_seconds",
    "FinSentinel HTTP request latency.",
    ["method", "route"],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

HTTP_ACTIVE_REQUESTS = Gauge(
    "finsentinel_http_active_requests",
    "Current number of active FinSentinel HTTP requests.",
    ["method"],
)

HTTP_ERRORS = Counter(
    "finsentinel_http_errors_total",
    "Total FinSentinel HTTP 4xx and 5xx responses.",
    ["method", "route", "status"],
)


SECURITY_DENIALS = Counter(
    "finsentinel_security_denials_total",
    "Authentication and authorization denials.",
    ["route", "status"],
)

_observability_configured = False


def _route_name(
    request: Request,
) -> str:
    route = request.scope.get("route")

    route_path = getattr(
        route,
        "path",
        None,
    )

    if route_path:
        return str(route_path)

    return request.url.path


def _configure_tracing(
    app: FastAPI,
) -> None:
    enabled = os.getenv(
        "OTEL_TRACING_ENABLED",
        "false",
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import (
        FastAPIInstrumentor,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
    )

    service_name = os.getenv(
        "OTEL_SERVICE_NAME",
        "finsentinel-api",
    )

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "http://jaeger:4318/v1/traces",
    )

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.namespace": "finsentinel",
                "deployment.environment": os.getenv(
                    "APP_ENV",
                    "development",
                ),
            }
        )
    )

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        timeout=5,
    )

    provider.add_span_processor(
        BatchSpanProcessor(
            exporter
        )
    )

    trace.set_tracer_provider(
        provider
    )

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=(
            "/metrics,"
            "/health/live,"
            "/health/ready"
        ),
    )


def configure_observability(
    app: FastAPI,
) -> None:
    global _observability_configured

    if _observability_configured:
        return

    _observability_configured = True

    @app.middleware("http")
    async def prometheus_http_metrics(
        request: Request,
        call_next,
    ):
        method = request.method

        HTTP_ACTIVE_REQUESTS.labels(
            method=method
        ).inc()

        started = time.perf_counter()

        status_code = 500

        try:
            response = await call_next(
                request
            )

            status_code = (
                response.status_code
            )

            return response

        finally:
            duration = (
                time.perf_counter()
                - started
            )

            route = _route_name(
                request
            )

            status = str(
                status_code
            )

            HTTP_REQUESTS.labels(
                method=method,
                route=route,
                status=status,
            ).inc()

            HTTP_REQUEST_DURATION.labels(
                method=method,
                route=route,
            ).observe(
                duration
            )


            if status_code in {
                401,
                403,
            }:
                SECURITY_DENIALS.labels(
                    route=route,
                    status=status,
                ).inc()

            if status_code >= 400:
                HTTP_ERRORS.labels(
                    method=method,
                    route=route,
                    status=status,
                ).inc()

            HTTP_ACTIVE_REQUESTS.labels(
                method=method
            ).dec()

    _configure_tracing(
        app
    )
