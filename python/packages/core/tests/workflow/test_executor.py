# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import (
    Executor,
    ExecutorCompletedEvent,
    ExecutorInvokedEvent,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
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


async def test_executor_completed_event_none_when_no_messages_sent():
    """Test that ExecutorCompletedEvent.data is None when no messages are sent."""
    from typing_extensions import Never

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
    assert completed_events[0].data is None

    # Verify the output was still yielded correctly
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
