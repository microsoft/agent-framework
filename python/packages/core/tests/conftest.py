# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pytest import fixture


@fixture
def enable_instrumentation(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def span_exporter(monkeypatch, enable_instrumentation: bool, enable_sensitive_data: bool) -> Generator[SpanExporter]:
    """Fixture to remove environment variables for ObservabilitySettings."""

    env_vars = [
        "ENABLE_INSTRUMENTATION",
        "ENABLE_SENSITIVE_DATA",
        "ENABLE_CONSOLE_EXPORTERS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OTEL_SERVICE_NAME",
        "OTEL_SERVICE_VERSION",
        "OTEL_RESOURCE_ATTRIBUTES",
    ]

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)  # type: ignore
    monkeypatch.setenv("ENABLE_INSTRUMENTATION", str(enable_instrumentation))  # type: ignore
    if not enable_instrumentation:
        # we overwrite sensitive data for tests
        enable_sensitive_data = False
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", str(enable_sensitive_data))  # type: ignore
    import importlib

    from opentelemetry import trace

    import agent_framework.observability as observability

    # Reload the module to ensure a clean state for tests, then create a
    # fresh ObservabilitySettings instance and patch the module attribute.
    importlib.reload(observability)

    # recreate observability settings with values from above and no file.
    observability_settings = observability.ObservabilitySettings(env_file_path="test.env")

    # Configure providers manually without calling _configure() to avoid OTLP imports
    if enable_instrumentation or enable_sensitive_data:
        from opentelemetry.sdk.trace import TracerProvider

        tracer_provider = TracerProvider(resource=observability_settings._resource)
        trace.set_tracer_provider(tracer_provider)

    monkeypatch.setattr(observability, "OBSERVABILITY_SETTINGS", observability_settings, raising=False)  # type: ignore

    with (
        patch("agent_framework.observability.OBSERVABILITY_SETTINGS", observability_settings),
        patch("agent_framework.observability.configure_otel_providers"),
    ):
        exporter = InMemorySpanExporter()
        if enable_instrumentation or enable_sensitive_data:
            tracer_provider = trace.get_tracer_provider()
            if not hasattr(tracer_provider, "add_span_processor"):
                raise RuntimeError("Tracer provider does not support adding span processors.")

            tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore

        yield exporter
        # Clean up
        exporter.clear()
