# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any, cast

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder, step, workflow
from agent_framework._workflows._events import WorkflowErrorDetails, WorkflowEvent
from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._runner_context import InProcRunnerContext, MessageType, WorkflowMessage
from agent_framework._workflows._state import State
from agent_framework._workflows._workflow import Workflow
from agent_framework._workflows._workflow_context import WorkflowContext
from agent_framework.observability import (
    OtelAttr,
    create_processing_span,
    create_workflow_span,
)


def _span_attributes(span: Any) -> dict[str, Any]:
    attributes = span.attributes
    return dict(attributes) if attributes is not None else {}


def _assert_workflow_error_details(
    details: WorkflowErrorDetails,
    private_error_detail: str,
    enable_sensitive_data: bool,
) -> None:
    assert private_error_detail not in details.error_type
    if enable_sensitive_data:
        assert private_error_detail in details.message
        assert details.traceback is not None
        assert private_error_detail in details.traceback
    else:
        assert details.message == details.error_type
        assert details.traceback is None


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
    async def handle_message(self, message: str, ctx: WorkflowContext) -> None:
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
    async def handle_aggregated_data(self, messages: list[str], ctx: WorkflowContext) -> None:
        # Process aggregated messages from fan-in
        aggregated = f"aggregated: {', '.join(messages)}"
        self._processed_messages.append(aggregated)

    @property
    def processed_messages(self) -> list[Any]:
        """Access to processed messages for testing."""
        return self._processed_messages


async def test_span_creation_and_attributes(span_exporter: InMemorySpanExporter) -> None:
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
                "model_dump_json": lambda self: '{"id": "test-workflow-123", "type": "mock"}',  # pyright: ignore[reportUnknownLambdaType]
            },
        )(),
    )

    # Test all span types in nested context
    with create_workflow_span(
        OtelAttr.WORKFLOW_RUN_SPAN,
        {
            OtelAttr.WORKFLOW_ID: mock_workflow.id,
        },
    ) as workflow_span:
        workflow_span.add_event(OtelAttr.WORKFLOW_STARTED)
        sending_attributes: dict[str, str | int] = {
            OtelAttr.MESSAGE_TYPE: "ResponseMessage",
            OtelAttr.MESSAGE_DESTINATION_EXECUTOR_ID: "target-789",
        }
        with (
            create_processing_span(
                "executor-456", "TestExecutor", str(MessageType.STANDARD), "TestMessage"
            ) as processing_span,
            create_workflow_span(
                OtelAttr.MESSAGE_SEND_SPAN, sending_attributes, kind=trace.SpanKind.PRODUCER
            ) as sending_span,
        ):
            # Verify all spans are recording
            assert workflow_span is not None and workflow_span.is_recording()
            assert processing_span is not None and processing_span.is_recording()
            assert sending_span is not None and sending_span.is_recording()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 3

    # Check workflow span
    workflow_span = next(s for s in spans if s.name == "workflow.run")  # type: ignore[assignment, misc]
    assert workflow_span.kind == trace.SpanKind.INTERNAL  # type: ignore[attr-defined]
    assert workflow_span.attributes is not None  # type: ignore[attr-defined]
    assert workflow_span.attributes.get(OtelAttr.WORKFLOW_ID) == "test-workflow-123"  # type: ignore[attr-defined]
    assert workflow_span.events is not None  # type: ignore[attr-defined]
    event_names = [event.name for event in workflow_span.events]  # type: ignore[attr-defined]
    assert "workflow.started" in event_names

    # Check processing span - span name uses format "executor.process {executor_id}"
    processing_span = next(s for s in spans if s.name == "executor.process executor-456")  # type: ignore[assignment, misc]
    assert processing_span.kind == trace.SpanKind.INTERNAL  # type: ignore[attr-defined]
    assert processing_span.attributes is not None  # type: ignore[attr-defined]
    assert processing_span.attributes.get("executor.id") == "executor-456"  # type: ignore[attr-defined]
    assert processing_span.attributes.get("executor.type") == "TestExecutor"  # type: ignore[attr-defined]
    assert processing_span.attributes.get("message.type") == str(MessageType.STANDARD)  # type: ignore[attr-defined]
    assert processing_span.attributes.get("message.payload_type") == "TestMessage"  # type: ignore[attr-defined]

    # Check sending span
    sending_span = next(s for s in spans if s.name == "message.send")  # type: ignore[assignment, misc]
    assert sending_span.kind == trace.SpanKind.PRODUCER  # type: ignore[attr-defined]
    assert sending_span.attributes is not None  # type: ignore[attr-defined]
    assert sending_span.attributes.get("message.type") == "ResponseMessage"  # type: ignore[attr-defined]
    assert sending_span.attributes.get("message.destination_executor_id") == "target-789"  # type: ignore[attr-defined]


async def test_trace_context_handling(span_exporter: InMemorySpanExporter) -> None:
    """Test trace context propagation and handling in messages and executors."""
    state = State()
    ctx = InProcRunnerContext()
    executor = MockExecutor("test-executor")

    span_exporter.clear()

    # Test trace context propagation in messages
    workflow_ctx: WorkflowContext[str] = WorkflowContext(
        executor,
        ["source"],
        state,
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
    await executor.execute(
        "test message",
        ["source"],  # source_executor_ids
        state,  # state
        ctx,  # runner_context
        trace_contexts=[{"traceparent": "00-12345678901234567890123456789012-1234567890123456-01"}],
        source_span_ids=["1234567890123456"],
    )

    # Check that spans were created with proper attributes
    spans = span_exporter.get_finished_spans()
    # Processing spans now use executor_id as the span name
    processing_spans = [s for s in spans if _span_attributes(s).get("executor.id") == "test-executor"]
    sending_spans = [s for s in spans if s.name == "message.send"]

    assert len(processing_spans) >= 1
    assert len(sending_spans) >= 1

    # Verify processing span attributes
    processing_span = processing_spans[0]
    assert (
        processing_span.name == "executor.process test-executor"
    )  # Span name uses format "executor.process {executor_id}"
    assert processing_span.attributes is not None
    assert processing_span.attributes.get("executor.id") == "test-executor"
    assert processing_span.attributes.get("executor.type") == "MockExecutor"
    assert processing_span.attributes.get("message.type") == str(MessageType.STANDARD)
    assert processing_span.attributes.get("message.payload_type") == "str"


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_trace_context_disabled_when_tracing_disabled(
    enable_instrumentation: bool, span_exporter: InMemorySpanExporter
) -> None:
    """Test that no trace context is added when tracing is disabled."""
    # Tracing should be disabled by default
    executor = MockExecutor("test-executor")
    state = State()
    ctx = InProcRunnerContext()

    workflow_ctx: WorkflowContext[str] = WorkflowContext(
        executor,
        ["source"],
        state,
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


async def test_end_to_end_workflow_tracing(span_exporter: InMemorySpanExporter) -> None:
    """Test end-to-end tracing including workflow build, execution, and span linking with fan-in edges."""
    # Create executors for fan-in scenario
    executor1 = MockExecutor("executor1")
    executor2 = ProcessingExecutor("executor2", "second")
    executor3 = ProcessingExecutor("executor3", "third")
    aggregator = FanInAggregator("aggregator")

    # Create workflow with fan-in: executor1 -> [executor2, executor3] -> aggregator
    workflow = (
        WorkflowBuilder(start_executor=executor1)
        .add_fan_out_edges(executor1, [executor2, executor3])
        .add_fan_in_edges([executor2, executor3], aggregator)
        .build()
    )

    # Verify build span was created
    build_spans = [s for s in span_exporter.get_finished_spans() if s.name == "workflow.build"]
    assert len(build_spans) == 1

    build_span = build_spans[0]
    assert build_span.attributes is not None
    assert build_span.attributes.get(OtelAttr.WORKFLOW_ID) == workflow.id
    assert build_span.attributes.get("workflow.definition") is not None
    definition = build_span.attributes.get("workflow.definition")
    assert definition == workflow.to_json()

    # Check build events
    assert build_span.events is not None
    build_event_names = [event.name for event in build_span.events]
    assert "build.started" in build_event_names
    assert "build.validation_completed" in build_event_names
    assert "build.completed" in build_event_names

    # Clear spans to test workflow with name and description
    span_exporter.clear()

    # Test workflow with name and description - verify OTEL attributes
    WorkflowBuilder(
        name="Test Pipeline",
        description="Test workflow description",
        start_executor=MockExecutor("start"),
    ).build()

    build_spans_with_metadata = [s for s in span_exporter.get_finished_spans() if s.name == "workflow.build"]
    assert len(build_spans_with_metadata) == 1
    metadata_build_span = build_spans_with_metadata[0]
    assert metadata_build_span.attributes is not None
    assert metadata_build_span.attributes.get(OtelAttr.WORKFLOW_BUILDER_NAME) == "Test Pipeline"
    assert metadata_build_span.attributes.get(OtelAttr.WORKFLOW_BUILDER_DESCRIPTION) == "Test workflow description"

    # Clear spans to separate build from run tracing
    span_exporter.clear()

    # Run workflow (this should create run spans)
    events: list[Any] = []
    with trace.get_tracer(__name__).start_as_current_span("outer") as outer_span:
        async for event in workflow.run("test input", stream=True):
            assert trace.get_current_span() is outer_span
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
    # Processing spans now use executor_id as the span name, filter by executor.id attribute
    workflow_spans = [s for s in spans if s.name == "workflow.run"]
    processing_spans = [s for s in spans if _span_attributes(s).get("executor.id") is not None]
    sending_spans = [s for s in spans if s.name == "message.send"]
    build_spans_after_run = [s for s in spans if s.name == "workflow.build"]

    assert len(workflow_spans) == 1
    assert len(processing_spans) >= 4  # executor1, executor2, executor3, aggregator
    assert len(sending_spans) >= 3  # Messages sent between executors
    assert len(build_spans_after_run) == 0  # No build spans should be present after clear

    # Verify workflow span events
    workflow_span = workflow_spans[0]
    assert workflow_span.parent is not None
    assert workflow_span.parent.span_id == outer_span.get_span_context().span_id
    assert workflow_span.context is not None
    assert all(
        processing_span.parent is not None and processing_span.parent.span_id == workflow_span.context.span_id
        for processing_span in processing_spans
    ), "Executor processing spans should be children of workflow.run"
    assert workflow_span.events is not None
    event_names = [event.name for event in workflow_span.events]
    assert "workflow.started" in event_names
    assert "workflow.completed" in event_names

    # Test fan-in span linking: find the aggregator's processing span
    aggregator_spans = [s for s in processing_spans if _span_attributes(s).get("executor.id") == "aggregator"]
    assert len(aggregator_spans) == 1

    aggregator_span = aggregator_spans[0]
    # The aggregator span should have links to the source spans (from executor2 and executor3)
    # This tests that FanInEdgeRunner properly handles multiple trace contexts and span IDs
    assert aggregator_span.links is not None

    # Find the sending spans from executor2 and executor3 by checking parent relationships
    executor2_processing_spans = [s for s in processing_spans if _span_attributes(s).get("executor.id") == "executor2"]
    executor3_processing_spans = [s for s in processing_spans if _span_attributes(s).get("executor.id") == "executor3"]

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


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_workflow_error_handling_in_tracing(
    span_exporter: InMemorySpanExporter, enable_sensitive_data: bool
) -> None:
    """Test that workflow errors are properly recorded in traces."""
    private_error_detail = "founder-secret-token"

    class FailingExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="failing_executor")

        @handler
        async def handle_message(self, message: str, ctx: WorkflowContext) -> None:
            raise ValueError(f"Test error: {private_error_detail}")

    failing_executor = FailingExecutor()
    workflow = WorkflowBuilder(start_executor=failing_executor).build()
    span_exporter.clear()

    # Run workflow and expect error
    events: list[WorkflowEvent[Any]] = []
    with pytest.raises(ValueError, match="Test error"):
        async for event in workflow.run("test input", stream=True):
            events.append(event)

    failed_events = [event for event in events if event.type == "failed"]
    assert len(failed_events) == 1
    assert failed_events[0].details is not None
    _assert_workflow_error_details(failed_events[0].details, private_error_detail, enable_sensitive_data)

    executor_failed_events = [event for event in events if event.type == "executor_failed"]
    assert len(executor_failed_events) == 1
    assert executor_failed_events[0].details is not None
    _assert_workflow_error_details(executor_failed_events[0].details, private_error_detail, enable_sensitive_data)

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
    assert workflow_span.attributes is not None
    assert workflow_span.attributes[OtelAttr.ERROR_TYPE] == "ValueError"
    assert (private_error_detail in (workflow_span.status.description or "")) is enable_sensitive_data

    workflow_error = next(event for event in workflow_span.events if event.name == "workflow.error")
    assert workflow_error.attributes is not None
    assert workflow_error.attributes["error.type"] == "ValueError"
    assert ("error.message" in workflow_error.attributes) is enable_sensitive_data
    if enable_sensitive_data:
        assert private_error_detail in str(workflow_error.attributes["error.message"])

    workflow_exception_events = [event for event in workflow_span.events if event.name == "exception"]
    assert bool(workflow_exception_events) is enable_sensitive_data
    if enable_sensitive_data:
        exception_attributes = workflow_exception_events[0].attributes
        assert exception_attributes is not None
        assert private_error_detail in str(exception_attributes.get("exception.message"))

    executor_spans = [span for span in spans if span.name == "executor.process failing_executor"]
    assert len(executor_spans) == 1
    executor_span = executor_spans[0]
    assert executor_span.attributes is not None
    assert executor_span.attributes[OtelAttr.ERROR_TYPE] == "ValueError"
    assert executor_span.status.status_code.name == "ERROR"
    assert (private_error_detail in (executor_span.status.description or "")) is enable_sensitive_data
    executor_exception_events = [event for event in executor_span.events if event.name == "exception"]
    assert bool(executor_exception_events) is enable_sensitive_data
    if enable_sensitive_data:
        exception_attributes = executor_exception_events[0].attributes
        assert exception_attributes is not None
        assert private_error_detail in str(exception_attributes.get("exception.message"))


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_functional_workflow_error_respects_sensitive_data(
    span_exporter: InMemorySpanExporter, enable_sensitive_data: bool
) -> None:
    """Functional workflow spans should redact exception details unless explicitly enabled."""
    private_error_detail = "founder-secret-token"

    @step
    async def failing_step(message: str) -> None:
        raise RuntimeError(f"Functional workflow failed: {message}")

    @workflow
    async def failing_workflow(message: str) -> None:
        await failing_step(message)

    workflow_instance = failing_workflow.build()
    span_exporter.clear()
    stream = workflow_instance.run(private_error_detail, stream=True)
    events: list[WorkflowEvent[Any]] = []
    with pytest.raises(RuntimeError, match="Functional workflow failed"):
        async for event in stream:
            events.append(event)

    failed_events = [event for event in events if event.type == "failed"]
    assert len(failed_events) == 1
    assert failed_events[0].details is not None
    _assert_workflow_error_details(failed_events[0].details, private_error_detail, enable_sensitive_data)

    executor_failed_events = [event for event in events if event.type == "executor_failed"]
    assert len(executor_failed_events) == 1
    assert executor_failed_events[0].details is not None
    _assert_workflow_error_details(executor_failed_events[0].details, private_error_detail, enable_sensitive_data)

    spans = span_exporter.get_finished_spans()
    workflow_spans = [span for span in spans if span.name == "workflow.run"]
    assert len(workflow_spans) == 1
    span = workflow_spans[0]
    assert span.attributes is not None
    assert span.attributes[OtelAttr.ERROR_TYPE] == "RuntimeError"
    assert span.status.status_code.name == "ERROR"
    assert (private_error_detail in (span.status.description or "")) is enable_sensitive_data

    error_event = next(event for event in span.events if event.name == "workflow.error")
    assert error_event.attributes is not None
    assert error_event.attributes["error.type"] == "RuntimeError"
    assert ("error.message" in error_event.attributes) is enable_sensitive_data
    if enable_sensitive_data:
        assert private_error_detail in str(error_event.attributes["error.message"])

    exception_events = [event for event in span.events if event.name == "exception"]
    assert bool(exception_events) is enable_sensitive_data
    if enable_sensitive_data:
        exception_attributes = exception_events[0].attributes
        assert exception_attributes is not None
        assert private_error_detail in str(exception_attributes.get("exception.message"))


@pytest.mark.parametrize("exception_type", [asyncio.CancelledError, GeneratorExit])
def test_workflow_span_lifecycle_exceptions_are_not_failures(
    span_exporter: InMemorySpanExporter,
    exception_type: type[BaseException],
) -> None:
    """Workflow span helpers should not classify lifecycle-control exceptions as failures."""
    span_exporter.clear()

    try:
        with create_workflow_span("workflow.lifecycle"):
            raise exception_type()
    except exception_type:
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code != trace.StatusCode.ERROR
    attributes = span.attributes
    if attributes is not None:
        assert OtelAttr.ERROR_TYPE not in attributes
    assert all(event.name != "exception" for event in span.events)


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
async def test_message_trace_context_serialization(span_exporter: InMemorySpanExporter) -> None:
    """Test that message trace context is properly serialized/deserialized."""
    ctx = InProcRunnerContext(InMemoryCheckpointStorage())

    # Create message with trace context
    message = WorkflowMessage(
        data="test",
        source_id="source",
        target_id="target",
        trace_contexts=[{"traceparent": "00-trace-span-01"}],
        source_span_ids=["span123"],
    )

    await ctx.send_message(message)

    # Create a checkpoint that includes the message
    checkpoint_id = await ctx.create_checkpoint("test_name", "test_hash", State(), None, 0)
    checkpoint = await ctx.load_checkpoint(checkpoint_id)
    assert checkpoint is not None

    # Check serialized message includes trace context
    serialized_msg = checkpoint.messages["source"][0]
    assert serialized_msg.trace_contexts == [{"traceparent": "00-trace-span-01"}]
    assert serialized_msg.source_span_ids == ["span123"]

    # Test deserialization
    await ctx.apply_checkpoint(checkpoint)
    restored_messages = await ctx.drain_messages()

    restored_msg = list(restored_messages.values())[0][0]
    assert restored_msg.trace_context == {"traceparent": "00-trace-span-01"}  # Test backward compatibility
    assert restored_msg.source_span_id == "span123"  # Test backward compatibility
    assert restored_msg.trace_contexts == [{"traceparent": "00-trace-span-01"}]  # Test new format
    assert restored_msg.source_span_ids == ["span123"]  # Test new format


@pytest.mark.parametrize("enable_sensitive_data", [True, False], indirect=True)
async def test_workflow_build_error_tracing(span_exporter: InMemorySpanExporter, enable_sensitive_data: bool) -> None:
    """Test that build errors are properly recorded in build spans."""

    # Create a valid builder, then clear the start executor to trigger a build-time ValueError
    builder = WorkflowBuilder(start_executor=MockExecutor(id="mock"))
    builder._start_executor = None  # type: ignore[assignment]

    with pytest.raises(ValueError):
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
    assert error_event.attributes.get("build.error.type") == "ValueError"
    assert ("build.error.message" in error_event.attributes) is enable_sensitive_data
    if enable_sensitive_data:
        assert "starting executor" in str(error_event.attributes["build.error.message"]).lower()

    assert build_span.attributes is not None
    assert build_span.attributes[OtelAttr.ERROR_TYPE] == "ValueError"
    assert ("starting executor" in (build_span.status.description or "").lower()) is enable_sensitive_data
    exception_events = [event for event in build_span.events if event.name == "exception"]
    assert bool(exception_events) is enable_sensitive_data
