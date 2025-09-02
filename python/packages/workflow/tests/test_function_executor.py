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

        @executor
        async def my_function(data: dict, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message(data)

        assert my_function.id == "my_function"

    def test_executor_decorator_without_parentheses(self):
        """Test @executor decorator works without parentheses."""

        @executor
        async def no_parens_function(data: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(data.upper())

        assert isinstance(no_parens_function, FunctionExecutor)
        assert no_parens_function.id == "no_parens_function"
        assert str in no_parens_function._handlers

        # Also test with single parameter function
        @executor
        async def simple_no_parens(value: int):
            return value * 2

        assert isinstance(simple_no_parens, FunctionExecutor)
        assert simple_no_parens.id == "simple_no_parens"
        assert int in simple_no_parens._handlers

    def test_union_output_types(self):
        """Test that union output types are properly inferred."""

        @executor
        async def multi_output(text: str, ctx: WorkflowContext[str | int]) -> None:
            if text.isdigit():
                await ctx.send_message(int(text))
            else:
                await ctx.send_message(text.upper())

        spec = multi_output._instance_handler_specs[0]
        assert set(spec["output_types"]) == {str, int}

    def test_none_output_type(self):
        """Test WorkflowContext[None] produces empty output types."""

        @executor
        async def no_output(data: Any, ctx: WorkflowContext[None]) -> None:
            # This executor doesn't send any messages
            pass

        spec = no_output._instance_handler_specs[0]
        assert spec["output_types"] == []

    def test_any_output_type(self):
        """Test WorkflowContext[Any] produces empty output types."""

        @executor
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

        # Wrong number of parameters (now accepts 1 or 2, so 0 or 3+ should fail)
        async def no_params() -> None:
            pass

        with pytest.raises(ValueError, match="one or two parameters"):
            FunctionExecutor(no_params)  # type: ignore

        async def too_many_params(data: str, ctx: WorkflowContext[str], extra: int) -> None:
            pass

        with pytest.raises(ValueError, match="one or two parameters"):
            FunctionExecutor(too_many_params)  # type: ignore

        # Missing message type annotation
        async def no_msg_type(data, ctx: WorkflowContext[str]) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="type annotation for the message"):
            FunctionExecutor(no_msg_type)  # type: ignore

        # Missing ctx annotation (only for 2-parameter functions)
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

        @executor
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

        @executor
        async def process_list(items: list[str], ctx: WorkflowContext[dict[str, int]]) -> None:
            result = {item: len(item) for item in items}
            await ctx.send_message(result)

        spec = process_list._instance_handler_specs[0]
        assert spec["message_type"] == list[str]
        assert spec["output_types"] == [dict[str, int]]

    def test_single_parameter_function(self):
        """Test FunctionExecutor with single-parameter functions."""

        @executor(id="simple_processor")
        async def process_simple(text: str):
            return text.upper()

        assert isinstance(process_simple, FunctionExecutor)
        assert process_simple.id == "simple_processor"
        assert str in process_simple._handlers

        # Check spec - single parameter functions have no output types since they can't send messages
        spec = process_simple._instance_handler_specs[0]
        assert spec["message_type"] is str
        assert spec["output_types"] == []
        assert spec["ctx_annotation"] is None

    def test_single_parameter_validation(self):
        """Test validation for single-parameter functions."""

        # Valid single-parameter function
        async def valid_single(data: int):
            return data * 2

        func_exec = FunctionExecutor(valid_single)
        assert int in func_exec._handlers

        # Single parameter with missing type annotation should still fail
        async def no_annotation(data):  # type: ignore
            pass

        with pytest.raises(ValueError, match="type annotation for the message"):
            FunctionExecutor(no_annotation)  # type: ignore

    def test_single_parameter_can_handle(self):
        """Test that single-parameter functions work with can_handle method."""

        @executor
        async def int_processor(value: int):
            return value * 2

        assert int_processor.can_handle(42)
        assert not int_processor.can_handle("hello")
        assert not int_processor.can_handle([])

    async def test_single_parameter_execution(self):
        """Test that single-parameter functions can be executed properly."""

        @executor(id="double")
        async def double_value(value: int):
            return value * 2

        # Since single-parameter functions can't send messages,
        # they're typically used as terminal nodes or for side effects
        WorkflowBuilder().set_start_executor(double_value).build()

        # For testing purposes, we can check that the handler is registered correctly
        assert double_value.can_handle(5)
        assert int in double_value._handlers
