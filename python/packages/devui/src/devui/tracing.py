# Copyright (c) Microsoft. All rights reserved.

"""OpenTelemetry integration for Agent Framework debug UI with real-time streaming."""

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Sequence
from opentelemetry.sdk.trace.export import SpanExporter

from .models import DebugStreamEvent, TraceSpan

logger = logging.getLogger(__name__)

class StreamingTraceExporter(SpanExporter):
    """OpenTelemetry span exporter that streams traces in real-time.
    
    Captures spans from Agent Framework's telemetry and immediately
    streams them as DebugStreamEvents for real-time UI updates.
    """
    
    def __init__(self, event_callback: Callable[[DebugStreamEvent], None]) -> None:
        """Initialize with callback for streaming trace events.
        
        Args:
            event_callback: Function to call with each trace event
        """
        self.event_callback = event_callback
        
    def export(self, spans: Sequence[Any]) -> Any:
        """Export spans by streaming them immediately.
        
        Args:
            spans: Sequence of OpenTelemetry spans
            
        Returns:
            SpanExportResult if OpenTelemetry available, None otherwise
        """
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult
            
            logger.info(f"StreamingTraceExporter.export called with {len(spans)} spans")
            
            for span in spans:
                logger.debug(f"Processing span: {span.name if hasattr(span, 'name') else 'unknown'}")
                
                # Extract thread ID from span attributes
                thread_id = self._extract_thread_id(span)
                logger.debug(f"Extracted thread_id: {thread_id}")
                
                if not thread_id:
                    # For debugging - create a fallback thread_id
                    thread_id = "default_session"
                    logger.warning(f"No thread_id found in span {span.name if hasattr(span, 'name') else 'unknown'}, using fallback")
                    
                # Convert to trace span and stream immediately
                trace_span = self._convert_to_trace_span(span)
                
                # Create stream event
                event = DebugStreamEvent(
                    type="trace_span",
                    trace_span=trace_span,
                    timestamp=datetime.now().isoformat(),
                    thread_id=thread_id
                )
                
                logger.info(f"Streaming trace event: {trace_span.operation_name}")
                
                # Stream the event
                self.event_callback(event)
                
            return SpanExportResult.SUCCESS
            
        except ImportError:
            logger.debug("OpenTelemetry not available for span export")
            return None
        except Exception as e:
            logger.error(f"Error streaming trace spans: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush spans (no-op for streaming).
        
        Args:
            timeout_millis: Timeout in milliseconds (unused)
            
        Returns:
            Always True for streaming
        """
        return True
    
    def _extract_thread_id(self, span: Any) -> Optional[str]:
        """Extract thread ID from span attributes."""
        if not hasattr(span, 'attributes') or not span.attributes:
            return None
            
        # Look for thread/session identifiers
        for key in ['thread_id', 'session_id', 'conversation_id']:
            if key in span.attributes:
                return str(span.attributes[key])
                
        # Fall back to trace ID as thread identifier
        if hasattr(span, 'context'):
            return str(span.context.trace_id)
            
        return None
    
    def _convert_to_trace_span(self, span: Any) -> TraceSpan:
        """Convert OpenTelemetry span to TraceSpan.
        
        Args:
            span: OpenTelemetry span
            
        Returns:
            TraceSpan for streaming
        """
        start_time = span.start_time / 1_000_000_000  # Convert from nanoseconds
        end_time = span.end_time / 1_000_000_000 if span.end_time else None
        duration_ms = ((end_time - start_time) * 1000) if end_time else None
        
        # Build clean span events
        events = []
        if hasattr(span, 'events'):
            for event in span.events:
                events.append({
                    "name": event.name,
                    "timestamp": event.timestamp / 1_000_000_000,
                    "attributes": dict(event.attributes) if event.attributes else {}
                })
        
        # Build raw span data with complete OpenTelemetry information
        raw_span = {
            "trace_id": str(span.context.trace_id),
            "span_kind": str(span.kind) if hasattr(span, 'kind') else None,
            "status_description": span.status.description if hasattr(span, 'status') and span.status.description else None,
            "instrumentation_scope": span.instrumentation_scope.name if hasattr(span, 'instrumentation_scope') else None,
            "resource_attributes": dict(span.resource.attributes) if hasattr(span, 'resource') and span.resource.attributes else {},
            "trace_state": str(span.context.trace_state) if hasattr(span.context, 'trace_state') and span.context.trace_state else None,
            "raw_attributes": dict(span.attributes) if span.attributes else {},
            "raw_events": [
                {
                    "name": event.name,
                    "timestamp": event.timestamp,  # Keep nanoseconds in raw
                    "attributes": dict(event.attributes) if event.attributes else {}
                }
                for event in (span.events if hasattr(span, 'events') else [])
            ]
        }
        
        # Add links if available
        if hasattr(span, 'links') and span.links:
            raw_span["links"] = [
                {
                    "trace_id": str(link.context.trace_id),
                    "span_id": str(link.context.span_id),
                    "attributes": dict(link.attributes) if link.attributes else {}
                }
                for link in span.links
            ]
        
        trace_span = TraceSpan(
            span_id=str(span.context.span_id),
            parent_span_id=str(span.parent.span_id) if span.parent else None,
            operation_name=span.name,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            attributes=dict(span.attributes) if span.attributes else {},
            events=events,
            status=str(span.status.status_code) if hasattr(span, 'status') else "OK",
            raw_span=raw_span
        )
                
        return trace_span

class TracingManager:
    """Manages OpenTelemetry integration for real-time trace streaming."""
    
    def __init__(self) -> None:
        """Initialize the tracing manager."""
        self._tracer_provider_initialized = False
        self._stream_callback: Optional[Callable[[DebugStreamEvent], None]] = None
        
    def setup_streaming_tracing(self, event_callback: Callable[[DebugStreamEvent], None]) -> None:
        """Initialize OpenTelemetry tracing with streaming integration.
        
        Args:
            event_callback: Function to call with each trace event for streaming
        """
        # Update the callback for this request
        self._stream_callback = event_callback
        
        if self._tracer_provider_initialized:
            logger.debug("Tracing already initialized, updated callback")
            return
            
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            
            # Only set up tracer provider if none exists
            if not hasattr(trace, '_TRACER_PROVIDER') or trace._TRACER_PROVIDER is None:
                provider = TracerProvider()
                
                # Add our streaming span processor
                processor = SimpleSpanProcessor(StreamingTraceExporter(self._get_callback_for_exporter))
                provider.add_span_processor(processor)
                
                trace.set_tracer_provider(provider)
                logger.info("Initialized OpenTelemetry streaming tracing for Agent Framework debug UI")
            else:
                # Add our processor to existing provider
                existing_provider = trace.get_tracer_provider()
                try:
                    processor = SimpleSpanProcessor(StreamingTraceExporter(self._get_callback_for_exporter))
                    existing_provider.add_span_processor(processor)  # type: ignore
                    logger.info("Added streaming processor to existing OpenTelemetry provider")
                except AttributeError:
                    logger.warning("Existing tracer provider doesn't support adding processors")
                except Exception as ex:
                    logger.error(f"Error adding processor to existing provider: {ex}")
                
            self._tracer_provider_initialized = True
                
        except ImportError:
            logger.warning("OpenTelemetry not available - tracing disabled")
        except Exception as e:
            logger.error(f"Error setting up streaming tracing: {e}")
            
    def _get_callback_for_exporter(self, event: DebugStreamEvent) -> None:
        """Wrapper to get current callback for exporter."""
        if self._stream_callback:
            self._stream_callback(event)
            
    def add_thread_id_to_current_span(self, thread_id: str) -> None:
        """Add thread ID to the current active span for session tracking.
        
        Args:
            thread_id: Thread identifier to add to span attributes
        """
        try:
            from opentelemetry import trace
            
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("thread_id", thread_id)
                logger.debug(f"Added thread_id {thread_id} to current span")
                
        except ImportError:
            logger.debug("OpenTelemetry not available for span tagging")
        except Exception as e:
            logger.error(f"Error adding thread_id to span: {e}")
            
    # Keeping this method for backward compatibility with existing API endpoint
    def get_session_traces(self, session_id: str) -> list:
        """Get session traces - returns empty for streaming-only implementation.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Empty list (traces are now streamed in real-time)
        """
        logger.info(f"get_session_traces called for {session_id} - traces are now streamed in real-time")
        return []