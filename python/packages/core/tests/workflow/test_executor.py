# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import Executor, WorkflowContext, handler


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
    assert executor.can_handle("text") is True
    assert executor.can_handle(42) is True
    assert executor.can_handle(3.14) is False


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
