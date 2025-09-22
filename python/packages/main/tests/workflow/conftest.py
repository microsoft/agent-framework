# Copyright (c) Microsoft. All rights reserved.


import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
@pytest.mark.parametrize("enable_workflow_otel", [True], indirect=True)
def span_exporter(otel_settings) -> SpanExporter:
    """Set up OpenTelemetry test infrastructure."""
    from opentelemetry import trace

    from agent_framework.observability import setup_observability

    # Use the built-in InMemorySpanExporter for better compatibility
    exporter = InMemorySpanExporter()
    setup_observability(enable_workflow_otel=True)
    trace.get_tracer_provider().add_span_processor(
        SimpleSpanProcessor(exporter)  # type: ignore[func-returns-value]
    )

    yield exporter

    # Clean up
    exporter.clear()
