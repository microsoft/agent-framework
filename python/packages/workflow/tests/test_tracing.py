# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import Generator
from typing import Any, cast

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_framework_workflow import WorkflowBuilder
from agent_framework_workflow._executor import Executor, handler
from agent_framework_workflow._runner_context import InProcRunnerContext, Message
from agent_framework_workflow._shared_state import SharedState
from agent_framework_workflow._telemetry import WorkflowTracer, workflow_tracer
from agent_framework_workflow._workflow import Workflow
from agent_framework_workflow._workflow_context import WorkflowContext


@pytest.fixture
def tracing_enabled() -> Generator[None, None, None]:
    """Enable tracing for tests."""
    original_value = os.environ.get("AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS")
    os.environ["AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS"] = "true"

    # Force reload the settings to pick up the environment variable
    from agent_framework_workflow._telemetry import WorkflowDiagnosticSettings

    workflow_tracer.settings = WorkflowDiagnosticSettings()

    yield

    # Restore original value
    if original_value is None:
        os.environ.pop("AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS", None)
    else:
        os.environ["AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS"] = original_value

    # Reload settings again
    workflow_tracer.settings = WorkflowDiagnosticSettings()


@pytest.fixture
def span_exporter(tracing_enabled: Any) -> Generator[InMemorySpanExporter, None, None]:
    """Set up OpenTelemetry test infrastructure."""
    # Use the built-in InMemorySpanExporter for better compatibility
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Store original tracer
    original_tracer = workflow_tracer.tracer

    # Set up our test tracer
    workflow_tracer.tracer = tracer_provider.get_tracer("agent_framework")

    yield exporter

    # Clean up
    exporter.clear()
    workflow_tracer.tracer = original_tracer


class MockExecutor(Executor):
    """Mock executor for testing."""

    def __init__(self, id: str = "mock_executor") -> None:
        super().__init__(id=id)
        # Use private field to avoid Pydantic validation
        self._processed_messages: list[str] = []

    @handler
    async def handle_message(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Handle string messages."""
        self._processed_messages.append(message)
        await ctx.send_message(f"processed: {message}")

    @property
    def processed_messages(self) -> list[str]:
        """Access to processed messages for testing."""
        return self._processed_messages


class SecondExecutor(Executor):
    """Second executor for testing message chains."""

    def __init__(self, id: str = "second_executor") -> None:
        super().__init__(id=id)
        # Use private field to avoid Pydantic validation
        self._processed_messages: list[str] = []

    @handler
    async def handle_message(self, message: str, ctx: WorkflowContext[None]) -> None:
        """Handle string messages."""
        self._processed_messages.append(message)

    @property
    def processed_messages(self) -> list[str]:
        """Access to processed messages for testing."""
        return self._processed_messages


class ProcessingExecutor(Executor):
    """Executor that processes and forwards messages with a custom prefix."""

    def __init__(self, id: str, prefix: str = "processed") -> None:
        super().__init__(id=id)
        # Use private field to avoid Pydantic validation
        self._processed_messages: list[str] = []
        self._prefix = prefix

    @handler
    async def handle_message(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Handle string messages and send them forward with prefix."""
        self._processed_messages.append(message)
        await ctx.send_message(f"{self._prefix}: {message}")

    @property
    def processed_messages(self) -> list[str]:
        return self._processed_messages


class FanInAggregator(Executor):
    """Fan-in aggregator that expects a list of inputs."""

    def __init__(self, id: str = "aggregator") -> None:
        super().__init__(id=id)
        # Use private field to avoid Pydantic validation
        self._processed_messages: list[Any] = []

    @handler
    async def handle_aggregated_data(self, messages: list[str], ctx: WorkflowContext[None]) -> None:
        # Process aggregated messages from fan-in
        aggregated = f"aggregated: {', '.join(messages)}"
        self._processed_messages.append(aggregated)

    @property
    def processed_messages(self) -> list[Any]:
        """Access to processed messages for testing."""
        return self._processed_messages


@pytest.mark.asyncio
async def test_workflow_tracer_configuration() -> None:
    """Test that workflow tracer can be enabled and disabled."""
    # Test disabled by default
    tracer = WorkflowTracer()
    assert not tracer.enabled

    # Test enabled with environment variable
    original_value = os.environ.get("AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS")
    os.environ["AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS"] = "true"

    # Force reload the settings to pick up the environment variable
    from agent_framework_workflow._telemetry import WorkflowDiagnosticSettings

    tracer.settings = WorkflowDiagnosticSettings()

    assert tracer.enabled

    # Restore original value
    if original_value is None:
        os.environ.pop("AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS", None)
    else:
        os.environ["AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS"] = original_value

    # Reload settings again
    tracer.settings = WorkflowDiagnosticSettings()


@pytest.mark.asyncio
async def test_span_creation_and_attributes(tracing_enabled: Any, span_exporter: InMemorySpanExporter) -> None:
    """Test creation and attributes of all span types (workflow, processing, sending)."""
    # Create a mock workflow object
    mock_workflow = cast(
        Workflow,
        type(
            "MockWorkflow",
            (),
            {
                "id": "test-workflow-123",
                "max_iterations": 100,
                "model_dump_json": lambda self: '{"id": "test-workflow-123", "type": "mock"}',
            },
        )(),
    )

    # Test all span types in nested context
    with workflow_tracer.create_workflow_run_span(mock_workflow) as workflow_span:
        workflow_tracer.add_workflow_event("workflow.started")

        with (
            workflow_tracer.create_processing_span("executor-456", "TestExecutor", "TestMessage") as processing_span,
            workflow_tracer.create_sending_span("ResponseMessage", "target-789") as sending_span,
        ):
            # Verify all spans are recording
            assert workflow_span is not None and workflow_span.is_recording()
            assert processing_span is not None and processing_span.is_recording()
            assert sending_span is not None and sending_span.is_recording()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 3

    # Check workflow span
    workflow_span = next(s for s in spans if s.name == "workflow.run")
    assert workflow_span.kind == trace.SpanKind.INTERNAL
    assert workflow_span.attributes is not None
    assert workflow_span.attributes.get("workflow.id") == "test-workflow-123"
    assert workflow_span.events is not None
    event_names = [event.name for event in workflow_span.events]
    assert "workflow.started" in event_names

    # Check processing span
    processing_span = next(s for s in spans if s.name == "executor.process")
    assert processing_span.kind == trace.SpanKind.INTERNAL
    assert processing_span.attributes is not None
    assert processing_span.attributes.get("executor.id") == "executor-456"
    assert processing_span.attributes.get("executor.type") == "TestExecutor"
    assert processing_span.attributes.get("message.type") == "TestMessage"

    # Check sending span
    sending_span = next(s for s in spans if s.name == "message.send")
    assert sending_span.kind == trace.SpanKind.PRODUCER
    assert sending_span.attributes is not None
    assert sending_span.attributes.get("message.type") == "ResponseMessage"
    assert sending_span.attributes.get("message.destination_executor_id") == "target-789"


@pytest.mark.asyncio
async def test_trace_context_handling(tracing_enabled: Any, span_exporter: InMemorySpanExporter) -> None:
    """Test trace context propagation and handling in messages and executors."""
    shared_state = SharedState()
    ctx = InProcRunnerContext()
    executor = MockExecutor("test-executor")

    # Test trace context propagation in messages
    workflow_ctx: WorkflowContext[str] = WorkflowContext(
        "test-executor",
        ["source"],
        shared_state,
        ctx,
        trace_contexts=[{"traceparent": "00-12345678901234567890123456789012-1234567890123456-01"}],
        source_span_ids=["1234567890123456"],
    )

    # Send a message (this should create a sending span and propagate trace context)
    await workflow_ctx.send_message("test message")

    # Check that message was created with trace context
    messages = await ctx.drain_messages()
    assert len(messages) == 1
    message_list = list(messages.values())[0]
    assert len(message_list) == 1
    message = message_list[0]
    assert message.trace_context is not None
    assert message.source_span_id is not None

    # Test executor trace context handling
    await executor.execute("test message", workflow_ctx)

    # Check that spans were created with proper attributes
    spans = span_exporter.get_finished_spans()
    processing_spans = [s for s in spans if s.name == "executor.process"]
    sending_spans = [s for s in spans if s.name == "message.send"]

    assert len(processing_spans) >= 1
    assert len(sending_spans) >= 1

    # Verify processing span attributes
    processing_span = processing_spans[0]
    assert processing_span.attributes is not None
    assert processing_span.attributes.get("executor.id") == "test-executor"
    assert processing_span.attributes.get("executor.type") == "MockExecutor"
    assert processing_span.attributes.get("message.type") == "str"


@pytest.mark.asyncio
async def test_trace_context_disabled_when_tracing_disabled() -> None:
    """Test that no trace context is added when tracing is disabled."""
    # Tracing should be disabled by default
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    workflow_ctx: WorkflowContext[str] = WorkflowContext(
        "test-executor",
        ["source"],
        shared_state,
        ctx,
    )

    # Send a message
    await workflow_ctx.send_message("test message")

    # Check that message was created without trace context
    messages = await ctx.drain_messages()
    message = list(messages.values())[0][0]

    # When tracing is disabled, trace_context should be None
    assert message.trace_context is None
    assert message.source_span_id is None


@pytest.mark.asyncio
async def test_end_to_end_workflow_tracing(tracing_enabled: Any, span_exporter: InMemorySpanExporter) -> None:
    """Test end-to-end tracing including workflow build, execution, and span linking with fan-in edges."""
    # Create executors for fan-in scenario
    executor1 = MockExecutor("executor1")
    executor2 = ProcessingExecutor("executor2", "second")
    executor3 = ProcessingExecutor("executor3", "third")
    aggregator = FanInAggregator("aggregator")

    # Create workflow with fan-in: executor1 -> [executor2, executor3] -> aggregator
    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor1)
        .add_fan_out_edges(executor1, [executor2, executor3])
        .add_fan_in_edges([executor2, executor3], aggregator)
        .build()
    )

    # Verify build span was created
    build_spans = [s for s in span_exporter.get_finished_spans() if s.name == "workflow.build"]
    assert len(build_spans) == 1

    build_span = build_spans[0]
    assert build_span.attributes is not None
    assert build_span.attributes.get("workflow.id") == workflow.id
    assert build_span.attributes.get("workflow.definition") is not None
    definition = build_span.attributes.get("workflow.definition")
    assert definition == workflow.model_dump_json()

    # Check build events
    assert build_span.events is not None
    build_event_names = [event.name for event in build_span.events]
    assert "build.started" in build_event_names
    assert "build.validation_completed" in build_event_names
    assert "build.completed" in build_event_names

    # Clear spans to separate build from run tracing
    span_exporter.clear()

    # Run workflow (this should create run spans)
    events = []
    async for event in workflow.run_streaming("test input"):
        events.append(event)

    # Verify workflow executed correctly
    assert len(executor1.processed_messages) == 1
    assert executor1.processed_messages[0] == "test input"
    assert len(executor2.processed_messages) == 1
    assert executor2.processed_messages[0] == "processed: test input"
    assert len(executor3.processed_messages) == 1
    assert executor3.processed_messages[0] == "processed: test input"  # executor3 receives from executor1 via fan-out
    assert len(aggregator.processed_messages) == 1
    # The aggregator should receive both processed messages from executor2 and executor3
    aggregated_msg = aggregator.processed_messages[0]
    assert "second: processed: test input" in aggregated_msg
    assert "third: processed: test input" in aggregated_msg

    # Check run spans (build spans should not be present after clear)
    spans = span_exporter.get_finished_spans()

    # Should have workflow span, processing spans, and sending spans
    workflow_spans = [s for s in spans if s.name == "workflow.run"]
    processing_spans = [s for s in spans if s.name == "executor.process"]
    sending_spans = [s for s in spans if s.name == "message.send"]
    build_spans_after_run = [s for s in spans if s.name == "workflow.build"]

    assert len(workflow_spans) == 1
    assert len(processing_spans) >= 4  # executor1, executor2, executor3, aggregator
    assert len(sending_spans) >= 3  # Messages sent between executors
    assert len(build_spans_after_run) == 0  # No build spans should be present after clear

    # Verify workflow span events
    workflow_span = workflow_spans[0]
    assert workflow_span.events is not None
    event_names = [event.name for event in workflow_span.events]
    assert "workflow.started" in event_names
    assert "workflow.completed" in event_names

    # Test fan-in span linking: find the aggregator's processing span
    aggregator_spans = [s for s in processing_spans if s.attributes and s.attributes.get("executor.id") == "aggregator"]
    assert len(aggregator_spans) == 1

    aggregator_span = aggregator_spans[0]
    # The aggregator span should have links to the source spans (from executor2 and executor3)
    # This tests that FanInEdgeRunner properly handles multiple trace contexts and span IDs
    assert aggregator_span.links is not None

    # Find the sending spans from executor2 and executor3 by checking parent relationships
    executor2_processing_spans = [
        s for s in processing_spans if s.attributes and s.attributes.get("executor.id") == "executor2"
    ]
    executor3_processing_spans = [
        s for s in processing_spans if s.attributes and s.attributes.get("executor.id") == "executor3"
    ]

    # Get span IDs from processing spans
    executor2_processing_span_ids = {format(s.context.span_id, "016x") for s in executor2_processing_spans if s.context}
    executor3_processing_span_ids = {format(s.context.span_id, "016x") for s in executor3_processing_spans if s.context}

    executor2_sending_spans = [
        s for s in sending_spans if s.parent and format(s.parent.span_id, "016x") in executor2_processing_span_ids
    ]
    executor3_sending_spans = [
        s for s in sending_spans if s.parent and format(s.parent.span_id, "016x") in executor3_processing_span_ids
    ]

    # Verify that we have sending spans from both executors
    assert len(executor2_sending_spans) >= 1, "Should have at least one sending span from executor2"
    assert len(executor3_sending_spans) >= 1, "Should have at least one sending span from executor3"

    # Verify that the aggregator span links point to the correct source spans
    linked_span_ids = {link.context.span_id for link in aggregator_span.links}

    # Should have links from both executor2 and executor3's sending spans
    executor2_span_ids = {s.context.span_id for s in executor2_sending_spans if s.context}
    executor3_span_ids = {s.context.span_id for s in executor3_sending_spans if s.context}

    # At least one span from each executor should be linked
    assert bool(linked_span_ids & executor2_span_ids), "Aggregator should link to executor2's sending span"
    assert bool(linked_span_ids & executor3_span_ids), "Aggregator should link to executor3's sending span"

    # Should have at least 2 links (one from each source executor)
    assert len(aggregator_span.links) >= 2, f"Expected at least 2 links, got {len(aggregator_span.links)}"


@pytest.mark.asyncio
async def test_workflow_error_handling_in_tracing(tracing_enabled: Any, span_exporter: InMemorySpanExporter) -> None:
    """Test that workflow errors are properly recorded in traces."""

    class FailingExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="failing_executor")

        @handler
        async def handle_message(self, message: str, ctx: WorkflowContext[None]) -> None:
            raise ValueError("Test error")

    failing_executor = FailingExecutor()
    workflow = WorkflowBuilder().set_start_executor(failing_executor).build()

    # Run workflow and expect error
    with pytest.raises(ValueError, match="Test error"):
        async for _ in workflow.run_streaming("test input"):
            pass

    spans = span_exporter.get_finished_spans()

    # Find workflow span
    workflow_spans = [s for s in spans if s.name == "workflow.run"]
    assert len(workflow_spans) == 1

    workflow_span = workflow_spans[0]

    # Verify error event and status are recorded
    assert workflow_span.events is not None
    event_names = [event.name for event in workflow_span.events]
    assert "workflow.started" in event_names
    assert "workflow.error" in event_names
    assert workflow_span.status.status_code.name == "ERROR"


@pytest.mark.asyncio
async def test_message_trace_context_serialization() -> None:
    """Test that message trace context is properly serialized/deserialized."""
    ctx = InProcRunnerContext()

    # Create message with trace context
    message = Message(
        data="test",
        source_id="source",
        target_id="target",
        trace_contexts=[{"traceparent": "00-trace-span-01"}],
        source_span_ids=["span123"],
    )

    await ctx.send_message(message)

    # Get checkpoint state (which serializes messages)
    state = await ctx.get_checkpoint_state()

    # Check serialized message includes trace context
    serialized_msg = state["messages"]["source"][0]
    assert serialized_msg["trace_contexts"] == [{"traceparent": "00-trace-span-01"}]
    assert serialized_msg["source_span_ids"] == ["span123"]

    # Test deserialization
    await ctx.set_checkpoint_state(state)
    restored_messages = await ctx.drain_messages()

    restored_msg = list(restored_messages.values())[0][0]
    assert restored_msg.trace_context == {"traceparent": "00-trace-span-01"}  # Test backward compatibility
    assert restored_msg.source_span_id == "span123"  # Test backward compatibility
    assert restored_msg.trace_contexts == [{"traceparent": "00-trace-span-01"}]  # Test new format
    assert restored_msg.source_span_ids == ["span123"]  # Test new format


@pytest.mark.asyncio
async def test_workflow_build_error_tracing(tracing_enabled: Any, span_exporter: InMemorySpanExporter) -> None:
    """Test that build errors are properly recorded in build spans."""

    # Test validation error by not setting start executor
    builder = WorkflowBuilder()

    with pytest.raises(ValueError, match="Starting executor must be set"):
        builder.build()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    build_span = spans[0]
    assert build_span.name == "workflow.build"

    # Verify error status and events
    assert build_span.status.status_code.name == "ERROR"
    assert build_span.events is not None

    event_names = [event.name for event in build_span.events]
    assert "build.started" in event_names
    assert "build.error" in event_names

    # Check error event attributes
    error_events = [event for event in build_span.events if event.name == "build.error"]
    assert len(error_events) == 1

    error_event = error_events[0]
    assert error_event.attributes is not None
    assert "Starting executor must be set" in str(error_event.attributes.get("build.error.message"))
    assert error_event.attributes.get("build.error.type") == "ValueError"
