# Copyright (c) Microsoft. All rights reserved.


import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
@pytest.mark.parametrize("enable_workflow_otel", [True], indirect=True)
def span_exporter(otel_settings) -> SpanExporter:
    """Set up OpenTelemetry test infrastructure."""
    from agent_framework.observability import OTEL_SETTINGS, setup_telemetry

    # Use the built-in InMemorySpanExporter for better compatibility
    exporter = InMemorySpanExporter()
    setup_telemetry(enable_workflow_otel=True)
    if not OTEL_SETTINGS._tracer_provider:
        raise RuntimeError("Tracer provider not initialized")
    OTEL_SETTINGS._tracer_provider.add_span_processor(
        SimpleSpanProcessor(exporter)  # type: ignore[func-returns-value]
    )

    yield exporter

    # Clean up
    exporter.clear()
