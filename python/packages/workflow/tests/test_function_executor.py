# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest
from agent_framework.workflow import (
    FunctionExecutor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    executor,
)


class TestFunctionExecutor:
    """Test suite for FunctionExecutor and @executor decorator."""

    def test_function_executor_basic(self):
        """Test basic FunctionExecutor creation and validation."""

        async def process_string(text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(text.upper())

        func_exec = FunctionExecutor(process_string)

        # Check that handler was registered
        assert len(func_exec._handlers) == 1
        assert str in func_exec._handlers

        # Check instance handler spec was created
        assert len(func_exec._instance_handler_specs) == 1
        spec = func_exec._instance_handler_specs[0]
        assert spec["name"] == "process_string"
        assert spec["message_type"] is str
        assert spec["output_types"] == [str]

    def test_executor_decorator(self):
        """Test @executor decorator creates proper FunctionExecutor."""

        @executor(id="test_executor")
        async def process_int(value: int, ctx: WorkflowContext[int]) -> None:
            await ctx.send_message(value * 2)

        assert isinstance(process_int, FunctionExecutor)
        assert process_int.id == "test_executor"
        assert int in process_int._handlers

        # Check spec
        spec = process_int._instance_handler_specs[0]
        assert spec["message_type"] is int
        assert spec["output_types"] == [int]

    def test_executor_decorator_without_id(self):
        """Test @executor decorator uses function name as default ID."""

        @executor()
        async def my_function(data: dict, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message(data)

        assert my_function.id == "my_function"

    def test_union_output_types(self):
        """Test that union output types are properly inferred."""

        @executor()
        async def multi_output(text: str, ctx: WorkflowContext[str | int]) -> None:
            if text.isdigit():
                await ctx.send_message(int(text))
            else:
                await ctx.send_message(text.upper())

        spec = multi_output._instance_handler_specs[0]
        assert set(spec["output_types"]) == {str, int}

    def test_none_output_type(self):
        """Test WorkflowContext[None] produces empty output types."""

        @executor()
        async def no_output(data: Any, ctx: WorkflowContext[None]) -> None:
            # This executor doesn't send any messages
            pass

        spec = no_output._instance_handler_specs[0]
        assert spec["output_types"] == []

    def test_any_output_type(self):
        """Test WorkflowContext[Any] produces empty output types."""

        @executor()
        async def any_output(data: str, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message("result")

        spec = any_output._instance_handler_specs[0]
        assert spec["output_types"] == []

    def test_validation_errors(self):
        """Test various validation errors in function signatures."""

        # Non-async function - this will cause runtime validation error
        def sync_func(data: str, ctx: WorkflowContext[str]) -> None:
            pass

        with pytest.raises(TypeError, match="@executor expects an async function"):
            FunctionExecutor(sync_func)  # type: ignore

        # Wrong number of parameters
        async def wrong_params(data: str) -> None:
            pass

        with pytest.raises(ValueError, match="exactly two parameters"):
            FunctionExecutor(wrong_params)  # type: ignore

        # Missing message type annotation
        async def no_msg_type(data, ctx: WorkflowContext[str]) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="type annotation for the message"):
            FunctionExecutor(no_msg_type)  # type: ignore

        # Missing ctx annotation
        async def no_ctx_type(data: str, ctx) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="annotated as WorkflowContext"):
            FunctionExecutor(no_ctx_type)  # type: ignore

        # Wrong ctx type
        async def wrong_ctx_type(data: str, ctx: str) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="WorkflowContext\\[T\\]"):
            FunctionExecutor(wrong_ctx_type)  # type: ignore

        # Unparameterized WorkflowContext
        async def unparameterized_ctx(data: str, ctx: WorkflowContext) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="concrete T"):
            FunctionExecutor(unparameterized_ctx)  # type: ignore

    async def test_execution_in_workflow(self):
        """Test that FunctionExecutor works properly in a workflow."""

        @executor(id="upper")
        async def to_upper(text: str, ctx: WorkflowContext[str]) -> None:
            result = text.upper()
            await ctx.send_message(result)

        @executor(id="reverse")
        async def reverse_text(text: str, ctx: WorkflowContext[Any]) -> None:
            result = text[::-1]
            await ctx.add_event(WorkflowCompletedEvent(result))

        workflow = WorkflowBuilder().add_edge(to_upper, reverse_text).set_start_executor(to_upper).build()

        # Run workflow
        events = await workflow.run("hello world")
        completed = events.get_completed_event()

        assert completed is not None
        assert completed.data == "DLROW OLLEH"

    def test_can_handle_method(self):
        """Test that can_handle method works with instance handlers."""

        @executor()
        async def string_processor(text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(text)

        assert string_processor.can_handle("hello")
        assert not string_processor.can_handle(123)
        assert not string_processor.can_handle([])

    def test_duplicate_handler_registration(self):
        """Test that registering duplicate handlers raises an error."""

        async def first_handler(text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(text)

        func_exec = FunctionExecutor(first_handler)

        # Try to register another handler for the same type
        async def second_handler(message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message)

        with pytest.raises(ValueError, match="Handler for type .* already registered"):
            func_exec.register_instance_handler(
                name="second",
                func=second_handler,
                message_type=str,
                ctx_annotation=WorkflowContext[str],
                output_types=[str],
            )

    def test_complex_type_annotations(self):
        """Test with complex type annotations like List[str], Dict[str, int], etc."""
        from typing import Dict, List

        @executor()
        async def process_list(items: List[str], ctx: WorkflowContext[Dict[str, int]]) -> None:
            result = {item: len(item) for item in items}
            await ctx.send_message(result)

        spec = process_list._instance_handler_specs[0]
        assert spec["message_type"] is List[str]
        assert spec["output_types"] == [Dict[str, int]]
