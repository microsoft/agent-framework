# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

import pytest
from typing_extensions import Never

from agent_framework import (
    ChatMessage,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
    handler,
    response_handler,
)


# Module-level types for string forward reference tests
@dataclass
class ForwardRefMessage:
    content: str


@dataclass
class ForwardRefTypeA:
    value: str


@dataclass
class ForwardRefTypeB:
    value: int


@dataclass
class ForwardRefResponse:
    result: str


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
    """Test that executor_invoked event (type='executor_invoked') contains the input message data."""

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

    workflow = WorkflowBuilder(start_executor=upper).add_edge(upper, collector).build()

    events = await workflow.run("hello world")
    invoked_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_invoked"]

    assert len(invoked_events) == 2

    # First invoked event should be for 'upper' executor with input "hello world"
    upper_invoked = next(e for e in invoked_events if e.executor_id == "upper")
    assert upper_invoked.data == "hello world"

    # Second invoked event should be for 'collector' executor with input "HELLO WORLD"
    collector_invoked = next(e for e in invoked_events if e.executor_id == "collector")
    assert collector_invoked.data == "HELLO WORLD"


async def test_executor_completed_event_contains_sent_messages():
    """Test that event (type='executor_completed') contains the messages sent via ctx.send_message()."""

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

    workflow = WorkflowBuilder(start_executor=sender).add_edge(sender, collector).build()

    events = await workflow.run("hello")
    completed_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_completed"]

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
    """Test that WorkflowEvent(type='executor_completed').data includes yielded outputs."""

    class YieldOnlyExecutor(Executor):
        @handler
        async def handle(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output(text.upper())

    executor = YieldOnlyExecutor(id="yielder")
    workflow = WorkflowBuilder(start_executor=executor).build()

    events = await workflow.run("test")
    completed_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_completed"]

    assert len(completed_events) == 1
    assert completed_events[0].executor_id == "yielder"
    # Yielded outputs are now included in executor_completed event (type='executor_completed').data
    assert completed_events[0].data == ["TEST"]

    # Verify the output was also yielded as an output event (type='output')
    output_events = [e for e in events if e.type == "output"]
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

    workflow = WorkflowBuilder(start_executor=processor).add_edge(processor, collector).build()

    input_request = Request(query="hello", limit=3)
    events = await workflow.run(input_request)

    invoked_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_invoked"]
    completed_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_completed"]

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
    """Test that executor_invoked event (type='executor_invoked').data captures original input, not mutated input."""

    @executor(id="Mutator")
    async def mutator(messages: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        # The handler mutates the input list by appending new messages
        original_len = len(messages)
        messages.append(ChatMessage(role="assistant", text="Added by executor"))
        await ctx.send_message(messages)
        # Verify mutation happened
        assert len(messages) == original_len + 1

    workflow = WorkflowBuilder(start_executor=mutator).build()

    # Run with a single user message
    input_messages = [ChatMessage(role="user", text="hello")]
    events = await workflow.run(input_messages)

    # Find the invoked event for the Mutator executor
    invoked_events = [e for e in events if isinstance(e, WorkflowEvent) and e.type == "executor_invoked"]
    assert len(invoked_events) == 1
    mutator_invoked = invoked_events[0]

    # The event data should contain ONLY the original input (1 user message)
    assert mutator_invoked.executor_id == "Mutator"
    assert len(mutator_invoked.data) == 1, (
        f"Expected 1 message (original input), got {len(mutator_invoked.data)}: "
        f"{[m.text for m in mutator_invoked.data]}"
    )
    assert mutator_invoked.data[0].text == "hello"


# region: Tests for @handler decorator with explicit input_type and output_type


class TestHandlerExplicitTypes:
    """Test suite for @handler decorator with explicit input_type and output_type parameters."""

    def test_handler_with_explicit_input_type(self):
        """Test that explicit input_type takes precedence over introspection."""
        from typing import Any

        class ExplicitInputExecutor(Executor):
            @handler(input=str)
            async def handle(self, message: Any, ctx: WorkflowContext) -> None:
                pass

        exec_instance = ExplicitInputExecutor(id="explicit_input")

        # Handler should be registered for str (explicit), not Any (introspected)
        assert str in exec_instance._handlers
        assert len(exec_instance._handlers) == 1

        # Can handle str messages
        assert exec_instance.can_handle(Message(data="hello", source_id="mock"))
        # Cannot handle int messages (since explicit type is str)
        assert not exec_instance.can_handle(Message(data=42, source_id="mock"))

    def test_handler_with_explicit_output_type(self):
        """Test that explicit output works when input is also specified."""

        class ExplicitOutputExecutor(Executor):
            @handler(input=str, output=int)
            async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
                pass

        exec_instance = ExplicitOutputExecutor(id="explicit_output")

        # Handler spec should have int as output type (explicit)
        handler_func = exec_instance._handlers[str]
        assert handler_func._handler_spec["output_types"] == [int]

        # Executor output_types property should reflect explicit type
        assert int in exec_instance.output_types
        assert str not in exec_instance.output_types

    def test_handler_with_explicit_input_and_output_types(self):
        """Test that both explicit input_type and output_type work together."""
        from typing import Any

        class ExplicitBothExecutor(Executor):
            @handler(input=dict, output=list)
            async def handle(self, message: Any, ctx: WorkflowContext) -> None:
                pass

        exec_instance = ExplicitBothExecutor(id="explicit_both")

        # Handler should be registered for dict (explicit input type)
        assert dict in exec_instance._handlers
        assert len(exec_instance._handlers) == 1

        # Output type should be list (explicit)
        handler_func = exec_instance._handlers[dict]
        assert handler_func._handler_spec["output_types"] == [list]

        # Verify can_handle
        assert exec_instance.can_handle(Message(data={"key": "value"}, source_id="mock"))
        assert not exec_instance.can_handle(Message(data="string", source_id="mock"))

    def test_handler_with_explicit_union_input_type(self):
        """Test that explicit union input_type is handled correctly."""
        from typing import Any

        class UnionInputExecutor(Executor):
            @handler(input=str | int)
            async def handle(self, message: Any, ctx: WorkflowContext) -> None:
                pass

        exec_instance = UnionInputExecutor(id="union_input")

        # Handler should be registered for the union type
        # The union type itself is stored as the key
        assert len(exec_instance._handlers) == 1

        # Can handle both str and int messages
        assert exec_instance.can_handle(Message(data="hello", source_id="mock"))
        assert exec_instance.can_handle(Message(data=42, source_id="mock"))
        # Cannot handle float
        assert not exec_instance.can_handle(Message(data=3.14, source_id="mock"))

    def test_handler_with_explicit_union_output_type(self):
        """Test that explicit union output is normalized to a list."""
        from typing import Any

        class UnionOutputExecutor(Executor):
            @handler(input=bytes, output=str | int | bool)
            async def handle(self, message: Any, ctx: WorkflowContext) -> None:
                pass

        exec_instance = UnionOutputExecutor(id="union_output")

        # Output types should be a list with all union members
        assert set(exec_instance.output_types) == {str, int, bool}

    def test_handler_explicit_types_precedence_over_introspection(self):
        """Test that explicit types always take precedence over introspected types."""

        class PrecedenceExecutor(Executor):
            # Introspection would give: input=str, output=[int]
            # Explicit gives: input=bytes, output=[float]
            @handler(input=bytes, output=float)
            async def handle(self, message: str, ctx: WorkflowContext[int]) -> None:
                pass

        exec_instance = PrecedenceExecutor(id="precedence")

        # Should use explicit input type (bytes), not introspected (str)
        assert bytes in exec_instance._handlers
        assert str not in exec_instance._handlers

        # Should use explicit output type (float), not introspected (int)
        assert float in exec_instance.output_types
        assert int not in exec_instance.output_types

    def test_handler_fallback_to_introspection_when_no_explicit_types(self):
        """Test that introspection is used when no explicit types are provided."""

        class IntrospectedExecutor(Executor):
            @handler
            async def handle(self, message: str, ctx: WorkflowContext[int]) -> None:
                pass

        exec_instance = IntrospectedExecutor(id="introspected")

        # Should use introspected types
        assert str in exec_instance._handlers
        assert int in exec_instance.output_types

    def test_handler_explicit_mode_requires_input(self):
        """Test that using any explicit type param requires input to be specified."""

        # Only explicit input - output defaults to empty (no introspection)
        class OnlyInputExecutor(Executor):
            @handler(input=bytes)
            async def handle(self, message: str, ctx: WorkflowContext[int]) -> None:
                pass

        exec_input = OnlyInputExecutor(id="only_input")
        assert bytes in exec_input._handlers  # Explicit
        assert exec_input.output_types == []  # No output types (not introspected)

        # Only explicit output without input should raise error
        with pytest.raises(ValueError, match="must specify 'input' type"):

            class OnlyOutputExecutor(Executor):
                @handler(output=float)
                async def handle(self, message: str, ctx: WorkflowContext[int]) -> None:
                    pass

        # Only explicit workflow_output without input should raise error
        with pytest.raises(ValueError, match="must specify 'input' type"):

            class OnlyWorkflowOutputExecutor(Executor):
                @handler(workflow_output=bool)
                async def handle(self, message: str, ctx: WorkflowContext[int, str]) -> None:
                    pass

    def test_handler_explicit_input_type_allows_no_message_annotation(self):
        """Test that explicit input_type allows handler without message type annotation."""

        class NoAnnotationExecutor(Executor):
            @handler(input=str)
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = NoAnnotationExecutor(id="no_annotation")

        # Should work with explicit input_type
        assert str in exec_instance._handlers
        assert exec_instance.can_handle(Message(data="hello", source_id="mock"))

    def test_handler_multiple_handlers_mixed_explicit_and_introspected(self):
        """Test executor with multiple handlers, some with explicit types and some introspected."""

        class MixedExecutor(Executor):
            @handler(input=str, output=int)
            async def handle_explicit(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

            @handler
            async def handle_introspected(self, message: float, ctx: WorkflowContext[bool]) -> None:
                pass

        exec_instance = MixedExecutor(id="mixed")

        # Should have both handlers
        assert len(exec_instance._handlers) == 2
        assert str in exec_instance._handlers  # Explicit
        assert float in exec_instance._handlers  # Introspected

        # Should have both output types
        assert int in exec_instance.output_types  # Explicit
        assert bool in exec_instance.output_types  # Introspected

    def test_handler_with_string_forward_reference_input_type(self):
        """Test that string forward references work for input_type."""

        class StringRefExecutor(Executor):
            @handler(input="ForwardRefMessage")
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = StringRefExecutor(id="string_ref")

        # Should resolve the string to the actual type
        assert ForwardRefMessage in exec_instance._handlers
        assert exec_instance.can_handle(Message(data=ForwardRefMessage("hello"), source_id="mock"))

    def test_handler_with_string_forward_reference_union(self):
        """Test that string forward references work with union types."""

        class StringUnionExecutor(Executor):
            @handler(input="ForwardRefTypeA | ForwardRefTypeB")
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = StringUnionExecutor(id="string_union")

        # Should handle both types
        assert exec_instance.can_handle(Message(data=ForwardRefTypeA("hello"), source_id="mock"))
        assert exec_instance.can_handle(Message(data=ForwardRefTypeB(42), source_id="mock"))

    def test_handler_with_string_forward_reference_output_type(self):
        """Test that string forward references work for output_type."""

        class StringOutputExecutor(Executor):
            @handler(input=str, output="ForwardRefResponse")
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = StringOutputExecutor(id="string_output")

        # Should resolve the string output type
        assert ForwardRefResponse in exec_instance.output_types

    def test_handler_with_explicit_workflow_output_type(self):
        """Test that explicit workflow_output works when input is also specified."""

        class ExplicitWorkflowOutputExecutor(Executor):
            @handler(input=str, workflow_output=bool)
            async def handle(self, message: str, ctx: WorkflowContext[int]) -> None:
                pass

        exec_instance = ExplicitWorkflowOutputExecutor(id="explicit_workflow_output")

        # Handler spec should have bool as workflow_output_type (explicit)
        handler_func = exec_instance._handlers[str]
        assert handler_func._handler_spec["workflow_output_types"] == [bool]

        # Executor workflow_output_types property should reflect explicit type
        assert bool in exec_instance.workflow_output_types
        # output_types should be empty (explicit mode, output not specified)
        assert exec_instance.output_types == []

    def test_handler_with_explicit_workflow_output_and_output(self):
        """Test that explicit workflow_output works alongside explicit output."""

        class PrecedenceExecutor(Executor):
            @handler(input=int, output=float, workflow_output=str)
            async def handle(self, message: int, ctx: WorkflowContext[int, bool]) -> None:
                pass

        exec_instance = PrecedenceExecutor(id="precedence")

        # All types should come from explicit params
        assert int in exec_instance._handlers
        assert float in exec_instance.output_types
        assert str in exec_instance.workflow_output_types
        # Introspected types should NOT be present
        assert bool not in exec_instance.workflow_output_types

    def test_handler_with_all_explicit_types(self):
        """Test that all three explicit type parameters work together."""
        from typing import Any

        class AllExplicitExecutor(Executor):
            @handler(input=str, output=int, workflow_output=bool)
            async def handle(self, message: Any, ctx: WorkflowContext) -> None:
                pass

        exec_instance = AllExplicitExecutor(id="all_explicit")

        # Check input type
        assert str in exec_instance._handlers
        assert exec_instance.can_handle(Message(data="hello", source_id="mock"))

        # Check output_type
        assert int in exec_instance.output_types

        # Check workflow_output_type
        assert bool in exec_instance.workflow_output_types

    def test_handler_with_union_workflow_output_type(self):
        """Test that union types work for workflow_output."""

        class UnionWorkflowOutputExecutor(Executor):
            @handler(input=str, workflow_output=str | int)
            async def handle(self, message: str, ctx: WorkflowContext) -> None:
                pass

        exec_instance = UnionWorkflowOutputExecutor(id="union_workflow_output")

        # Should include both types from union
        assert str in exec_instance.workflow_output_types
        assert int in exec_instance.workflow_output_types

    def test_handler_with_string_forward_reference_workflow_output_type(self):
        """Test that string forward references work for workflow_output_type."""

        class StringWorkflowOutputExecutor(Executor):
            @handler(input=str, workflow_output="ForwardRefResponse")
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = StringWorkflowOutputExecutor(id="string_workflow_output")

        # Should resolve the string workflow_output_type
        assert ForwardRefResponse in exec_instance.workflow_output_types

    def test_handler_with_string_forward_reference_union_workflow_output_type(self):
        """Test that string forward reference union types work for workflow_output_type."""

        class StringUnionWorkflowOutputExecutor(Executor):
            @handler(input=str, workflow_output="ForwardRefTypeA | ForwardRefTypeB")
            async def handle(self, message, ctx: WorkflowContext) -> None:  # type: ignore[no-untyped-def]
                pass

        exec_instance = StringUnionWorkflowOutputExecutor(id="string_union_workflow_output")

        # Should resolve both types from string union
        assert ForwardRefTypeA in exec_instance.workflow_output_types
        assert ForwardRefTypeB in exec_instance.workflow_output_types

    def test_handler_fallback_to_introspection_for_workflow_output_type(self):
        """Test that workflow_output_type falls back to introspection when not explicitly provided."""

        class IntrospectedWorkflowOutputExecutor(Executor):
            @handler
            async def handle(self, message: str, ctx: WorkflowContext[int, bool]) -> None:
                pass

        exec_instance = IntrospectedWorkflowOutputExecutor(id="introspected_workflow_output")

        # Should use introspected types from WorkflowContext[int, bool]
        assert int in exec_instance.output_types
        assert bool in exec_instance.workflow_output_types


# endregion: Tests for @handler decorator with explicit input_type and output_type
