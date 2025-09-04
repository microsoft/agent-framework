# Copyright (c) Microsoft. All rights reserved.

from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework._pydantic import AFBaseSettings
from opentelemetry.trace import Link, NoOpTracer, SpanKind, StatusCode, get_current_span, get_tracer
from opentelemetry.trace.span import SpanContext
from opentelemetry.util.types import Attributes

if TYPE_CHECKING:
    from ._workflow import Workflow


class EdgeGroupDeliveryStatus(Enum):
    """Enum for edge group delivery status values."""

    DELIVERED = "delivered"
    DROPPED_TYPE_MISMATCH = "dropped type mismatch"
    DROPPED_TARGET_MISMATCH = "dropped target mismatch"
    DROPPED_CONDITION_FALSE = "dropped condition evaluated to false"
    EXCEPTION = "exception"
    BUFFERED = "buffered"


# Span name constants
_WORKFLOW_BUILD_SPAN = "workflow.build"
_WORKFLOW_RUN_SPAN = "workflow.run"
_EXECUTOR_PROCESS_SPAN = "executor.process"
_MESSAGE_SEND_SPAN = "message.send"
_EDGE_GROUP_PROCESS_SPAN = "edge_group.process"


class WorkflowDiagnosticSettings(AFBaseSettings):
    """Settings for workflow tracing diagnostics."""

    env_prefix: ClassVar[str] = "AGENT_FRAMEWORK_WORKFLOW_"
    enable_otel_diagnostics: bool = False

    @property
    def ENABLED(self) -> bool:
        return self.enable_otel_diagnostics


class WorkflowTracer:
    """Central tracing coordinator for workflow system.

    Manages OpenTelemetry span creation and relationships for:
    - Workflow build spans (workflow.build)
    - Workflow execution spans (workflow.run)
    - Executor processing spans (executor.process)
    - Message sending spans (message.send)
    - Edge group processing spans (edge_group.process)

    Implements span linking for causality without unwanted nesting.
    """

    def __init__(self) -> None:
        self.settings = WorkflowDiagnosticSettings()
        self.tracer = get_tracer("agent_framework") if self.settings.ENABLED else NoOpTracer()

    @property
    def enabled(self) -> bool:
        return self.settings.ENABLED

    def create_workflow_run_span(self, workflow: "Workflow") -> Any:
        """Create a workflow execution span."""
        attributes: dict[str, str | int] = {
            "workflow.id": workflow.id,
        }

        return self.tracer.start_as_current_span(_WORKFLOW_RUN_SPAN, kind=SpanKind.INTERNAL, attributes=attributes)

    def create_workflow_build_span(self) -> Any:
        """Create a workflow build span."""
        return self.tracer.start_as_current_span(_WORKFLOW_BUILD_SPAN, kind=SpanKind.INTERNAL)

    def create_processing_span(
        self,
        executor_id: str,
        executor_type: str,
        message_type: str,
        source_trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ) -> Any:
        """Create an executor processing span with optional links to source spans.

        Processing spans are created as children of the current workflow span and
        linked (not nested) to the source publishing spans for causality tracking.
        This supports multiple links for fan-in scenarios.
        """
        # Create links to source spans for causality without nesting
        links = []
        if source_trace_contexts and source_span_ids:
            # Create links for all source spans (supporting fan-in with multiple sources)
            for trace_context, span_id in zip(source_trace_contexts, source_span_ids, strict=False):
                try:
                    # Extract trace and span IDs from the trace context
                    # This is a simplified approach - in production you'd want more robust parsing
                    traceparent = trace_context.get("traceparent", "")
                    if traceparent:
                        # traceparent format: "00-{trace_id}-{parent_span_id}-{trace_flags}"
                        parts = traceparent.split("-")
                        if len(parts) >= 3:
                            trace_id_hex = parts[1]
                            # Use the source_span_id that was saved from the publishing span

                            # Create span context for linking
                            span_context = SpanContext(
                                trace_id=int(trace_id_hex, 16),
                                span_id=int(span_id, 16),
                                is_remote=True,
                            )
                            links.append(Link(span_context))
                except (ValueError, TypeError, AttributeError):
                    # If linking fails, continue without link (graceful degradation)
                    pass

        return self.tracer.start_as_current_span(
            _EXECUTOR_PROCESS_SPAN,
            kind=SpanKind.INTERNAL,
            attributes={
                "executor.id": executor_id,
                "executor.type": executor_type,
                "message.type": message_type,
            },
            links=links,
        )

    def create_sending_span(self, message_type: str, target_executor_id: str | None = None) -> Any:
        """Create a message send span.

        Sending spans are created as children of the current processing span
        to track message emission for distributed tracing.
        """
        attributes: dict[str, str] = {
            "message.type": message_type,
        }
        if target_executor_id is not None:
            attributes["message.destination_executor_id"] = target_executor_id

        return self.tracer.start_as_current_span(
            _MESSAGE_SEND_SPAN,
            kind=SpanKind.PRODUCER,
            attributes=attributes,
        )

    def create_edge_group_processing_span(
        self,
        edge_group_type: str,
        edge_group_id: str | None = None,
        message_source_id: str | None = None,
        message_target_id: str | None = None,
        source_trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ) -> Any:
        """Create an edge group processing span with optional links to source spans.

        Edge group processing spans track the processing operations in edge runners
        before message delivery, including condition checking and routing decisions.
        Links to source spans provide causality tracking without unwanted nesting.

        Args:
            edge_group_type: The type of the edge group (class name).
            edge_group_id: The unique ID of the edge group.
            message_source_id: The source ID of the message being processed.
            message_target_id: The target ID of the message being processed.
            source_trace_contexts: Optional trace contexts from source spans for linking.
            source_span_ids: Optional source span IDs for linking.
        """
        attributes: dict[str, str] = {
            "edge_group.type": edge_group_type,
        }

        if edge_group_id is not None:
            attributes["edge_group.id"] = edge_group_id
        if message_source_id is not None:
            attributes["message.source_id"] = message_source_id
        if message_target_id is not None:
            attributes["message.target_id"] = message_target_id

        # Create links to source spans for causality without nesting
        links = []
        if source_trace_contexts and source_span_ids:
            # Create links for all source spans (supporting fan-in with multiple sources)
            for trace_context, span_id in zip(source_trace_contexts, source_span_ids, strict=False):
                try:
                    # Extract trace and span IDs from the trace context
                    # This is a simplified approach - in production you'd want more robust parsing
                    traceparent = trace_context.get("traceparent", "")
                    if traceparent:
                        # traceparent format: "00-{trace_id}-{parent_span_id}-{trace_flags}"
                        parts = traceparent.split("-")
                        if len(parts) >= 3:
                            trace_id_hex = parts[1]
                            # Use the source_span_id that was saved from the publishing span

                            # Create span context for linking
                            span_context = SpanContext(
                                trace_id=int(trace_id_hex, 16),
                                span_id=int(span_id, 16),
                                is_remote=True,
                            )
                            links.append(Link(span_context))
                except (ValueError, TypeError, AttributeError):
                    # If linking fails, continue without link (graceful degradation)
                    pass

        return self.tracer.start_as_current_span(
            _EDGE_GROUP_PROCESS_SPAN,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            links=links,
        )

    def set_edge_group_span_attributes(self, delivered: bool, delivery_status: EdgeGroupDeliveryStatus) -> None:
        """Set edge group span attributes for delivery status.

        Args:
            delivered: Whether the message was delivered.
            delivery_status: The delivery status from EdgeGroupDeliveryStatus enum.
        """
        span = get_current_span()
        if span and span.is_recording():
            span.set_attributes({
                "edge_group.delivered": delivered,
                "edge_group.delivery_status": delivery_status.value,
            })

    def add_workflow_event(self, event_name: str, attributes: Attributes | None = None) -> None:
        """Add an event to the current workflow span.

        Args:
            event_name: Name of the event (e.g., "workflow.started", "workflow.completed")
            attributes: Optional attributes to attach to the event
        """
        span = get_current_span()
        if span and span.is_recording():
            span.add_event(event_name, attributes)

    def add_workflow_error_event(self, error: Exception, attributes: Attributes | None = None) -> None:
        """Add an error event to the current workflow span.

        Args:
            error: The exception that occurred
            attributes: Optional additional attributes to attach to the event
        """
        span = get_current_span()
        if span and span.is_recording():
            event_attributes: dict[str, str | bool | int | float] = {
                "error.message": str(error),
                "error.type": type(error).__name__,
            }
            if attributes:
                # Safely merge attributes, ensuring type compatibility
                for key, value in attributes.items():
                    if isinstance(value, (str, bool, int, float)):
                        event_attributes[key] = value
            span.add_event("workflow.error", event_attributes)
            span.set_status(StatusCode.ERROR, str(error))

    def set_workflow_build_span_attributes(self, workflow: "Workflow") -> None:
        """Set workflow attributes on the current span.

        Args:
            workflow: The workflow instance to extract attributes from
        """
        span = get_current_span()
        if span and span.is_recording():
            span.set_attributes({
                "workflow.id": workflow.id,
                "workflow.definition": workflow.model_dump_json(by_alias=True),
            })

    def add_build_event(self, event_name: str, attributes: Attributes | None = None) -> None:
        """Add an event to the current workflow build span.

        Args:
            event_name: Name of the build event (e.g., "build.started", "build.validation_completed")
            attributes: Optional attributes to attach to the event
        """
        span = get_current_span()
        if span and span.is_recording():
            span.add_event(event_name, attributes)

    def add_build_error_event(self, error: Exception, attributes: Attributes | None = None) -> None:
        """Add an error event to the current workflow build span.

        Args:
            error: The exception that occurred during build
            attributes: Optional additional attributes to attach to the event
        """
        span = get_current_span()
        if span and span.is_recording():
            event_attributes: dict[str, str | bool | int | float] = {
                "build.error.message": str(error),
                "build.error.type": type(error).__name__,
            }
            if attributes:
                # Safely merge attributes, ensuring type compatibility
                for key, value in attributes.items():
                    if isinstance(value, (str, bool, int, float)):
                        event_attributes[key] = value
            span.add_event("build.error", event_attributes)
            span.set_status(StatusCode.ERROR, str(error))


# Global workflow tracer instance
workflow_tracer = WorkflowTracer()
