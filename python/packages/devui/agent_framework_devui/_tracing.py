# Copyright (c) Microsoft. All rights reserved.

"""Simplified tracing integration for Agent Framework Server."""

import logging
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .models import ResponseTraceEvent

logger = logging.getLogger(__name__)


class SimpleTraceCollector(SpanExporter):
    """Simple trace collector that captures spans for direct yielding."""

    def __init__(self, session_id: str | None = None, entity_id: str | None = None) -> None:
        """Initialize trace collector.

        Args:
            session_id: Session identifier for context
            entity_id: Entity identifier for context
        """
        self.session_id = session_id
        self.entity_id = entity_id
        self.collected_events: list[ResponseTraceEvent] = []

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        """Collect spans as trace events.

        Args:
            spans: Sequence of OpenTelemetry spans

        Returns:
            SpanExportResult indicating success
        """
        logger.debug(f"SimpleTraceCollector received {len(spans)} spans")

        try:
            for span in spans:
                trace_event = self._convert_span_to_trace_event(span)
                if trace_event:
                    self.collected_events.append(trace_event)
                    logger.debug(f"Collected trace event: {span.name}")

            return SpanExportResult.SUCCESS

        except Exception as e:
            logger.error(f"Error collecting trace spans: {e}")
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush spans (no-op for simple collection)."""
        return True

    def get_pending_events(self) -> list[ResponseTraceEvent]:
        """Get and clear pending trace events.

        Returns:
            List of collected trace events, clearing the internal list
        """
        events = self.collected_events.copy()
        self.collected_events.clear()
        return events

    def _convert_span_to_trace_event(self, span: Any) -> ResponseTraceEvent | None:
        """Convert OpenTelemetry span to ResponseTraceEvent.

        Args:
            span: OpenTelemetry span

        Returns:
            ResponseTraceEvent or None if conversion fails
        """
        try:
            start_time = span.start_time / 1_000_000_000  # Convert from nanoseconds
            end_time = span.end_time / 1_000_000_000 if span.end_time else None
            duration_ms = ((end_time - start_time) * 1000) if end_time else None

            # Build trace data
            trace_data = {
                "type": "trace_span",
                "span_id": str(span.context.span_id),
                "trace_id": str(span.context.trace_id),
                "parent_span_id": str(span.parent.span_id) if span.parent else None,
                "operation_name": span.name,
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "attributes": dict(span.attributes) if span.attributes else {},
                "status": str(span.status.status_code) if hasattr(span, "status") else "OK",
                "session_id": self.session_id,
                "entity_id": self.entity_id,
            }

            # Add events if available
            if hasattr(span, "events") and span.events:
                trace_data["events"] = [
                    {
                        "name": event.name,
                        "timestamp": event.timestamp / 1_000_000_000,
                        "attributes": dict(event.attributes) if event.attributes else {},
                    }
                    for event in span.events
                ]

            # Add error information if span failed
            if hasattr(span, "status") and span.status.status_code.name == "ERROR":
                trace_data["error"] = span.status.description or "Unknown error"

            return ResponseTraceEvent(type="trace_event", data=trace_data, timestamp=datetime.now().isoformat())

        except Exception as e:
            logger.warning(f"Failed to convert span {getattr(span, 'name', 'unknown')}: {e}")
            return None


@contextmanager
def capture_traces(
    session_id: str | None = None, entity_id: str | None = None
) -> Generator[SimpleTraceCollector, None, None]:
    """Context manager to capture traces during execution.

    Args:
        session_id: Session identifier for context
        entity_id: Entity identifier for context

    Yields:
        SimpleTraceCollector instance to get trace events from
    """
    collector = SimpleTraceCollector(session_id, entity_id)

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        # Get current tracer provider and add our collector
        provider = trace.get_tracer_provider()
        processor = SimpleSpanProcessor(collector)

        # Check if this is a real TracerProvider (not the default NoOpTracerProvider)
        if isinstance(provider, TracerProvider):
            provider.add_span_processor(processor)
            logger.debug(f"Added trace collector to TracerProvider for session: {session_id}, entity: {entity_id}")

            try:
                yield collector
            finally:
                # Clean up - shutdown processor
                try:
                    processor.shutdown()
                except Exception as e:
                    logger.debug(f"Error shutting down processor: {e}")
        else:
            logger.warning(f"No real TracerProvider available, got: {type(provider)}")
            yield collector

    except ImportError:
        logger.debug("OpenTelemetry not available")
        yield collector
    except Exception as e:
        logger.error(f"Error setting up trace capture: {e}")
        yield collector
