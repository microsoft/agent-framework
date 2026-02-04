# Copyright (c) Microsoft. All rights reserved.

import pytest
from typing_extensions import Never

from agent_framework import (
    ChatMessage,
    Executor,
    ExecutorCompletedEvent,
    ExecutorInvokedEvent,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    response_handler,
)


def test_executor_without_id():
    """Test that an executor without an ID raises an error when trying to run."""

    class MockExecutorWithoutID(Executor):
        """A mock executor that does not implement any handlers."""

        pass

    with pytest.raises(ValueError):
        MockExecutorWithoutID(id="")


def test_executor_handler_without_annotations():
    """Test that an executor with one handler without annotations raises an error when trying to run."""

    with pytest.raises(ValueError):

        class MockExecutorWithOneHandlerWithoutAnnotations(Executor):  # type: ignore
            """A mock executor with one handler that does not implement any annotations."""

            @handler
            async def handle(self, message, ctx) -> None:  # type: ignore
                """A mock handler that does not implement any annotations."""
                pass


def test_executor_invalid_handler_signature():
    """Test that an executor with an invalid handler signature raises an error when trying to run."""

    with pytest.raises(ValueError):

        class MockExecutorWithInvalidHandlerSignature(Executor):  # type: ignore
            """A mock executor with an invalid handler signature."""

            @handler  # type: ignore
            async def handle(self, message, other, ctx) -> None:  # type: ignore
                """A mock handler with an invalid signature."""
                pass


def test_executor_with_valid_handlers():
    """Test that an executor with valid handlers can be instantiated and run."""

    class MockExecutorWithValidHandlers(Executor):  # type: ignore
        """A mock executor with valid handlers."""

        @handler
        async def handle_text(self, text: str, ctx: WorkflowContext) -> None:  # type: ignore
            """A mock handler with a valid signature."""
            pass

        @handler
        async def handle_number(self, number: int, ctx: WorkflowContext) -> None:  # type: ignore
            """Another mock handler with a valid signature."""
            pass

    executor = MockExecutorWithValidHandlers(id="test")
    assert executor.id is not None
    assert len(executor._handlers) == 2  # type: ignore
    assert executor.can_handle(Message(data="text", source_id="mock")) is True
    assert executor.can_handle(Message(data=42, source_id="mock")) is True
    assert executor.can_handle(Message(data=3.14, source_id="mock")) is False


def test_executor_handlers_with_output_types():
    """Test that an executor with handlers that specify output types can be instantiated and run."""

    class MockExecutorWithOutputTypes(Executor):  # type: ignore
        """A mock executor with handlers that specify output types."""

        @handler
        async def handle_string(self, text: str, ctx: WorkflowContext[str]) -> None:  # type: ignore
            """A mock handler that outputs a string."""
            pass

        @handler
        async def handle_integer(self, number: int, ctx: WorkflowContext[int]) -> None:  # type: ignore
            """A mock handler that outputs an integer."""
            pass

    executor = MockExecutorWithOutputTypes(id="test")
    assert len(executor._handlers) == 2  # type: ignore

    string_handler = executor._handlers[str]  # type: ignore
    assert string_handler is not None
    assert string_handler._handler_spec is not None  # type: ignore
    assert string_handler._handler_spec["name"] == "handle_string"  # type: ignore
    assert string_handler._handler_spec["message_type"] is str  # type: ignore
    assert string_handler._handler_spec["output_types"] == [str]  # type: ignore

    int_handler = executor._handlers[int]  # type: ignore
    assert int_handler is not None
    assert int_handler._handler_spec is not None  # type: ignore
    assert int_handler._handler_spec["name"] == "handle_integer"  # type: ignore
    assert int_handler._handler_spec["message_type"] is int  # type: ignore
    assert int_handler._handler_spec["output_types"] == [int]  # type: ignore


async def test_executor_invoked_event_contains_input_data():
    """Test that ExecutorInvokedEvent contains the input message data."""

    class UpperCaseExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(text.upper())

    class CollectorExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext) -> None:
            pass

    upper = UpperCaseExecutor(id="upper")
    collector = CollectorExecutor(id="collector")

    workflow = WorkflowBuilder().add_edge(upper, collector).set_start_executor(upper).build()

    events = await workflow.run("hello world")
    invoked_events = [e for e in events if isinstance(e, ExecutorInvokedEvent)]

    assert len(invoked_events) == 2

    # First invoked event should be for 'upper' executor with input "hello world"
    upper_invoked = next(e for e in invoked_events if e.executor_id == "upper")
    assert upper_invoked.data == "hello world"

    # Second invoked event should be for 'collector' executor with input "HELLO WORLD"
    collector_invoked = next(e for e in invoked_events if e.executor_id == "collector")
    assert collector_invoked.data == "HELLO WORLD"


async def test_executor_completed_event_contains_sent_messages():
    """Test that ExecutorCompletedEvent contains the messages sent via ctx.send_message()."""

    class MultiSenderExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(f"{text}-first")
            await ctx.send_message(f"{text}-second")

    class CollectorExecutor(Executor):
        def __init__(self, id: str) -> None:
            super().__init__(id=id)
            self.received: list[str] = []

        @handler
        async def handle(self, text: str, ctx: WorkflowContext) -> None:
            self.received.append(text)

    sender = MultiSenderExecutor(id="sender")
    collector = CollectorExecutor(id="collector")

    workflow = WorkflowBuilder().add_edge(sender, collector).set_start_executor(sender).build()

    events = await workflow.run("hello")
    completed_events = [e for e in events if isinstance(e, ExecutorCompletedEvent)]

    # Sender should have completed with the sent messages
    sender_completed = next(e for e in completed_events if e.executor_id == "sender")
    assert sender_completed.data is not None
    assert sender_completed.data == ["hello-first", "hello-second"]

    # Collector should have completed with no sent messages (None)
    collector_completed_events = [e for e in completed_events if e.executor_id == "collector"]
    # Collector is called twice (once per message from sender)
    assert len(collector_completed_events) == 2
    for collector_completed in collector_completed_events:
        assert collector_completed.data is None


async def test_executor_completed_event_includes_yielded_outputs():
    """Test that ExecutorCompletedEvent.data includes yielded outputs."""

    from agent_framework import WorkflowOutputEvent

    class YieldOnlyExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output(text.upper())

    executor = YieldOnlyExecutor(id="yielder")
    workflow = WorkflowBuilder().set_start_executor(executor).build()

    events = await workflow.run("test")
    completed_events = [e for e in events if isinstance(e, ExecutorCompletedEvent)]

    assert len(completed_events) == 1
    assert completed_events[0].executor_id == "yielder"
    # Yielded outputs are now included in ExecutorCompletedEvent.data
    assert completed_events[0].data == ["TEST"]

    # Verify the output was also yielded as WorkflowOutputEvent
    output_events = [e for e in events if isinstance(e, WorkflowOutputEvent)]
    assert len(output_events) == 1
    assert output_events[0].data == "TEST"


async def test_executor_events_with_complex_message_types():
    """Test that executor events correctly capture complex message types."""
    from dataclasses import dataclass

    @dataclass
    class Request:
        query: str
        limit: int

    @dataclass
    class Response:
        results: list[str]

    class ProcessorExecutor(Executor):
        @handler
        async def handle(self, request: Request, ctx: WorkflowContext[Response]) -> None:
            response = Response(results=[request.query.upper()] * request.limit)
            await ctx.send_message(response)

    class CollectorExecutor(Executor):
        @handler
        async def handle(self, response: Response, ctx: WorkflowContext) -> None:
            pass

    processor = ProcessorExecutor(id="processor")
    collector = CollectorExecutor(id="collector")

    workflow = WorkflowBuilder().add_edge(processor, collector).set_start_executor(processor).build()

    input_request = Request(query="hello", limit=3)
    events = await workflow.run(input_request)

    invoked_events = [e for e in events if isinstance(e, ExecutorInvokedEvent)]
    completed_events = [e for e in events if isinstance(e, ExecutorCompletedEvent)]

    # Check processor invoked event has the Request object
    processor_invoked = next(e for e in invoked_events if e.executor_id == "processor")
    assert isinstance(processor_invoked.data, Request)
    assert processor_invoked.data.query == "hello"
    assert processor_invoked.data.limit == 3

    # Check processor completed event has the Response object
    processor_completed = next(e for e in completed_events if e.executor_id == "processor")
    assert processor_completed.data is not None
    assert len(processor_completed.data) == 1
    assert isinstance(processor_completed.data[0], Response)
    assert processor_completed.data[0].results == ["HELLO", "HELLO", "HELLO"]

    # Check collector invoked event has the Response object
    collector_invoked = next(e for e in invoked_events if e.executor_id == "collector")
    assert isinstance(collector_invoked.data, Response)
    assert collector_invoked.data.results == ["HELLO", "HELLO", "HELLO"]


def test_executor_output_types_property():
    """Test that the output_types property correctly identifies message output types."""

    # Test executor with no output types
    class NoOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext) -> None:
            pass

    executor = NoOutputExecutor(id="no_output")
    assert executor.output_types == []

    # Test executor with single output type
    class SingleOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int]) -> None:
            pass

    executor = SingleOutputExecutor(id="single_output")
    assert int in executor.output_types
    assert len(executor.output_types) == 1

    # Test executor with union output types
    class UnionOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int | str]) -> None:
            pass

    executor = UnionOutputExecutor(id="union_output")
    assert int in executor.output_types
    assert str in executor.output_types
    assert len(executor.output_types) == 2

    # Test executor with multiple handlers having different output types
    class MultiHandlerExecutor(Executor):
        @handler
        async def handle_string(self, text: str, ctx: WorkflowContext[int]) -> None:
            pass

        @handler
        async def handle_number(self, num: int, ctx: WorkflowContext[bool]) -> None:
            pass

    executor = MultiHandlerExecutor(id="multi_handler")
    assert int in executor.output_types
    assert bool in executor.output_types
    assert len(executor.output_types) == 2


def test_executor_workflow_output_types_property():
    """Test that the workflow_output_types property correctly identifies workflow output types."""

    # Test executor with no workflow output types
    class NoWorkflowOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int]) -> None:
            pass

    executor = NoWorkflowOutputExecutor(id="no_workflow_output")
    assert executor.workflow_output_types == []

    # Test executor with workflow output type (second type parameter)
    class WorkflowOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int, str]) -> None:
            pass

    executor = WorkflowOutputExecutor(id="workflow_output")
    assert str in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 1

    # Test executor with union workflow output types
    class UnionWorkflowOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int, str | bool]) -> None:
            pass

    executor = UnionWorkflowOutputExecutor(id="union_workflow_output")
    assert str in executor.workflow_output_types
    assert bool in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 2

    # Test executor with multiple handlers having different workflow output types
    class MultiHandlerWorkflowExecutor(Executor):
        @handler
        async def handle_string(self, text: str, ctx: WorkflowContext[int, str]) -> None:
            pass

        @handler
        async def handle_number(self, num: int, ctx: WorkflowContext[bool, float]) -> None:
            pass

    executor = MultiHandlerWorkflowExecutor(id="multi_workflow")
    assert str in executor.workflow_output_types
    assert float in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 2

    # Test executor with Never for message output (only workflow output)
    class YieldOnlyExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
            pass

    executor = YieldOnlyExecutor(id="yield_only")
    assert str in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 1
    # Should have no message output types
    assert executor.output_types == []


def test_executor_output_and_workflow_output_types_combined():
    """Test executor with both message and workflow output types."""

    class DualOutputExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int, str]) -> None:
            pass

    executor = DualOutputExecutor(id="dual")

    # Should have int as message output type
    assert int in executor.output_types
    assert len(executor.output_types) == 1

    # Should have str as workflow output type
    assert str in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 1

    # They should be distinct
    assert int not in executor.workflow_output_types
    assert str not in executor.output_types


def test_executor_output_types_includes_response_handlers():
    """Test that output_types includes types from response handlers."""
    from agent_framework import response_handler

    class RequestResponseExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int]) -> None:
            pass

        @response_handler
        async def handle_response(self, original_request: str, response: bool, ctx: WorkflowContext[float]) -> None:
            pass

    executor = RequestResponseExecutor(id="request_response")

    # Should include output types from both handler and response_handler
    assert int in executor.output_types
    assert float in executor.output_types
    assert len(executor.output_types) == 2


def test_executor_workflow_output_types_includes_response_handlers():
    """Test that workflow_output_types includes types from response handlers."""
    from agent_framework import response_handler

    class RequestResponseWorkflowExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int, str]) -> None:
            pass

        @response_handler
        async def handle_response(
            self, original_request: str, response: bool, ctx: WorkflowContext[float, bool]
        ) -> None:
            pass

    executor = RequestResponseWorkflowExecutor(id="request_response_workflow")

    # Should include workflow output types from both handler and response_handler
    assert str in executor.workflow_output_types
    assert bool in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 2

    # Verify message output types are separate
    assert int in executor.output_types
    assert float in executor.output_types
    assert len(executor.output_types) == 2


def test_executor_multiple_response_handlers_output_types():
    """Test that multiple response handlers contribute their output types."""

    class MultiResponseHandlerExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[int]) -> None:
            pass

        @response_handler
        async def handle_string_bool_response(
            self, original_request: str, response: bool, ctx: WorkflowContext[float]
        ) -> None:
            pass

        @response_handler
        async def handle_int_bool_response(
            self, original_request: int, response: bool, ctx: WorkflowContext[bool]
        ) -> None:
            pass

    executor = MultiResponseHandlerExecutor(id="multi_response")

    # Should include output types from all handlers and response handlers
    assert int in executor.output_types
    assert float in executor.output_types
    assert bool in executor.output_types
    assert len(executor.output_types) == 3


def test_executor_response_handler_union_output_types():
    """Test that response handlers with union output types contribute all types."""
    from agent_framework import response_handler

    class UnionResponseHandlerExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext) -> None:
            pass

        @response_handler
        async def handle_response(
            self, original_request: str, response: bool, ctx: WorkflowContext[int | str | float, bool | int]
        ) -> None:
            pass

    executor = UnionResponseHandlerExecutor(id="union_response")

    # Should include all output types from the union
    assert int in executor.output_types
    assert str in executor.output_types
    assert float in executor.output_types
    assert len(executor.output_types) == 3

    # Should include all workflow output types from the union
    assert bool in executor.workflow_output_types
    assert int in executor.workflow_output_types
    assert len(executor.workflow_output_types) == 2


async def test_executor_invoked_event_data_not_mutated_by_handler():
    """Test that ExecutorInvokedEvent.data captures original input, not mutated input."""

    @executor(id="Mutator")
    async def mutator(messages: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        # The handler mutates the input list by appending new messages
        original_len = len(messages)
        messages.append(ChatMessage(role="assistant", text="Added by executor"))
        await ctx.send_message(messages)
        # Verify mutation happened
        assert len(messages) == original_len + 1

    workflow = WorkflowBuilder().set_start_executor(mutator).build()

    # Run with a single user message
    input_messages = [ChatMessage(role="user", text="hello")]
    events = await workflow.run(input_messages)

    # Find the invoked event for the Mutator executor
    invoked_events = [e for e in events if isinstance(e, ExecutorInvokedEvent)]
    assert len(invoked_events) == 1
    mutator_invoked = invoked_events[0]

    # The event data should contain ONLY the original input (1 user message)
    assert mutator_invoked.executor_id == "Mutator"
    assert len(mutator_invoked.data) == 1, (
        f"Expected 1 message (original input), got {len(mutator_invoked.data)}: "
        f"{[m.text for m in mutator_invoked.data]}"
    )
    assert mutator_invoked.data[0].text == "hello"
