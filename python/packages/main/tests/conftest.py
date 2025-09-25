# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pytest import fixture


@fixture
def enable_otel(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture(autouse=True)
def span_exporter(monkeypatch, enable_otel: bool, enable_sensitive_data: bool) -> Generator[SpanExporter]:
    """Fixture to remove environment variables for OtelSettings."""

    env_vars = [
        "ENABLE_OTEL",
        "ENABLE_SENSITIVE_DATA",
        "OTLP_ENDPOINT",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "APPLICATIONINSIGHTS_LIVE_METRICS",
    ]

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)  # type: ignore
    monkeypatch.setenv("ENABLE_OTEL", str(enable_otel))  # type: ignore
    if not enable_otel:
        # we overwrite sensitive data for tests
        enable_sensitive_data = False
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", str(enable_sensitive_data))  # type: ignore
    import importlib

    from opentelemetry import trace

    import agent_framework.observability as observability

    # Reload the module to ensure a clean state for tests, then create a
    # fresh OtelSettings instance and patch the module attribute.
    importlib.reload(observability)

    # recreate otel settings with values from above and no file.
    otel = observability.OtelSettings(env_file_path="test.env")
    otel.setup_observability()
    monkeypatch.setattr(observability, "OTEL_SETTINGS", otel, raising=False)  # type: ignore
    exporter = InMemorySpanExporter()
    with (
        patch("agent_framework.observability.OTEL_SETTINGS", otel),
        patch("agent_framework.observability.setup_observability"),
    ):
        if enable_otel or enable_sensitive_data:
            trace.get_tracer_provider().add_span_processor(
                SimpleSpanProcessor(exporter)  # type: ignore[func-returns-value]
            )

        yield exporter
        # Clean up
        exporter.clear()
