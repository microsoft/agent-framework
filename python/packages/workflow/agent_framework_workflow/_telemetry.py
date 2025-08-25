# Copyright (c) Microsoft. All rights reserved.

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework._pydantic import AFBaseSettings
from opentelemetry.trace import Link, SpanKind, get_tracer
from opentelemetry.trace.span import SpanContext

if TYPE_CHECKING:
    from ._workflow import Workflow


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
    - Workflow execution spans (workflow.run)
    - Executor processing spans (executor.process)
    - Message publishing spans (message.publish)

    Implements span linking for causality without unwanted nesting.
    """

    def __init__(self) -> None:
        self.tracer = get_tracer("agent_framework")
        self.settings = WorkflowDiagnosticSettings()

    @property
    def enabled(self) -> bool:
        return self.settings.ENABLED

    def create_workflow_span(self, workflow: "Workflow") -> Any:
        """Create a workflow execution span."""
        if not self.enabled:
            return nullcontext()

        attributes = {
            "workflow.id": workflow.workflow_id,
            "workflow.definition": workflow.model_dump_json(),
        }

        return self.tracer.start_as_current_span("workflow.run", kind=SpanKind.INTERNAL, attributes=attributes)

    def create_processing_span(
        self,
        executor_id: str,
        executor_type: str,
        message_type: str,
        source_trace_context: dict[str, str] | None = None,
        source_span_id: str | None = None,
    ) -> Any:
        """Create an executor processing span with optional link to source span.

        Processing spans are created as children of the current workflow span and
        linked (not nested) to the source publishing span for causality tracking.
        """
        if not self.enabled:
            return nullcontext()

        # Create links to source spans for causality without nesting
        links = []
        if source_trace_context and source_span_id:
            try:
                # Extract trace and span IDs from the trace context
                # This is a simplified approach - in production you'd want more robust parsing
                traceparent = source_trace_context.get("traceparent", "")
                if traceparent:
                    # traceparent format: "00-{trace_id}-{parent_span_id}-{trace_flags}"
                    parts = traceparent.split("-")
                    if len(parts) >= 3:
                        trace_id_hex = parts[1]
                        # Use the source_span_id that was saved from the publishing span

                        # Create span context for linking
                        span_context = SpanContext(
                            trace_id=int(trace_id_hex, 16),
                            span_id=int(source_span_id, 16),
                            is_remote=True,
                        )
                        links.append(Link(span_context))
            except (ValueError, TypeError, AttributeError):
                # If linking fails, continue without link (graceful degradation)
                pass

        return self.tracer.start_as_current_span(
            "executor.process",
            kind=SpanKind.CONSUMER,
            attributes={
                "executor.id": executor_id,
                "executor.type": executor_type,
                "message.type": message_type,
            },
            links=links,
        )

    def create_publishing_span(self, message_type: str, target_executor_id: str | None = None) -> Any:
        """Create a message publishing span.

        Publishing spans are created as children of the current processing span
        to track message emission for distributed tracing.
        """
        if not self.enabled:
            return nullcontext()

        attributes: dict[str, str] = {
            "message.type": message_type,
        }
        if target_executor_id is not None:
            attributes["message.destination_executor_id"] = target_executor_id

        return self.tracer.start_as_current_span(
            "message.publish",
            kind=SpanKind.PRODUCER,
            attributes=attributes,
        )


# Global workflow tracer instance
workflow_tracer = WorkflowTracer()
