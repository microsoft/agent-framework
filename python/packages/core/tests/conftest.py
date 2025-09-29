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


@fixture
def span_exporter(monkeypatch, enable_otel: bool, enable_sensitive_data: bool) -> Generator[SpanExporter]:
    """Fixture to remove environment variables for ObservabilitySettings."""

    env_vars = [
        "ENABLE_OTEL",
        "ENABLE_SENSITIVE_DATA",
        "OTLP_ENDPOINT",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
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
    # fresh ObservabilitySettings instance and patch the module attribute.
    importlib.reload(observability)

    # recreate observability settings with values from above and no file.
    observability_settings = observability.ObservabilitySettings(env_file_path="test.env")
    observability_settings._configure()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(observability, "OBSERVABILITY_SETTINGS", observability_settings, raising=False)  # type: ignore

    with (
        patch("agent_framework.observability.OBSERVABILITY_SETTINGS", observability_settings),
        patch("agent_framework.observability.setup_observability"),
    ):
        exporter = InMemorySpanExporter()
        if enable_otel or enable_sensitive_data:
            tracer_provider = trace.get_tracer_provider()
            if not hasattr(tracer_provider, "add_span_processor"):
                raise RuntimeError("Tracer provider does not support adding span processors.")

            tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore

        yield exporter
        # Clean up
        exporter.clear()
