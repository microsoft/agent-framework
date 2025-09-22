# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pytest import fixture

if TYPE_CHECKING:
    from agent_framework.observability import OtelSettings


@fixture
def enable_otel(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_workflow_otel(request: Any) -> bool:
    """Fixture that returns a boolean indicating if workflow Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else False


@fixture
def otel_settings(
    patched_otel_settings: "OtelSettings", enable_otel: bool, enable_sensitive_data: bool, enable_workflow_otel: bool
) -> "OtelSettings":
    """Fixture to set environment variables for OtelSettings."""
    from agent_framework.observability import setup_observability

    setup_observability(
        enable_otel=enable_otel, enable_sensitive_data=enable_sensitive_data, enable_workflow_otel=enable_workflow_otel
    )

    return patched_otel_settings


@fixture(scope="function", autouse=True)
def patched_otel_settings(monkeypatch) -> "OtelSettings":  # type: ignore
    """Fixture to remove environment variables for OtelSettings."""

    env_vars = [
        "ENABLE_OTEL",
        "ENABLE_SENSITIVE_DATA",
        "ENABLE_WORKFLOW_OTEL",
        "OTLP_ENDPOINT",
        "APPLICATION_INSIGHTS_CONNECTION_STRING",
        "APPLICATION_INSIGHTS_LIVE_METRICS",
    ]

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)  # type: ignore
    # Instead of importing the name OTEL_SETTINGS into this module (which
    # creates a local binding), import the observability module and patch
    # its module-level OTEL_SETTINGS attribute. That way code that imports
    # `agent_framework.observability.OTEL_SETTINGS` will see the updated
    # value.
    import importlib

    import agent_framework.observability as observability

    # Reload the module to ensure a clean state for tests, then create a
    # fresh OtelSettings instance and patch the module attribute.
    importlib.reload(observability)

    otel = observability.OtelSettings(
        enable_otel=True, enable_workflow_otel=True, enable_sensitive_data=True, env_file_path="test.env"
    )  # reset to default values
    monkeypatch.setattr(observability, "OTEL_SETTINGS", otel, raising=False)  # type: ignore

    return otel


@pytest.fixture
@pytest.mark.parametrize("enable_workflow_otel", [True], indirect=True)
def span_exporter(otel_settings: "OtelSettings") -> Generator[SpanExporter]:
    """Set up OpenTelemetry test infrastructure."""
    from opentelemetry import trace

    # Use the built-in InMemorySpanExporter for better compatibility
    otel_settings.setup_observability()
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(
        SimpleSpanProcessor(exporter)  # type: ignore[func-returns-value]
    )

    yield exporter

    # Clean up
    exporter.clear()
