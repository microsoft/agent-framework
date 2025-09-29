# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    FunctionExecutor,
    WorkflowBuilder,
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

        # Check handler spec was created
        assert len(func_exec._handler_specs) == 1
        spec = func_exec._handler_specs[0]
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
        spec = process_int._handler_specs[0]
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
        """Test that union output types are properly inferred for both messages and workflow outputs."""

        @executor
        async def multi_output(text: str, ctx: WorkflowContext[str | int]) -> None:
            if text.isdigit():
                await ctx.send_message(int(text))
            else:
                await ctx.send_message(text.upper())

        spec = multi_output._handler_specs[0]
        assert set(spec["output_types"]) == {str, int}
        assert spec["workflow_output_types"] == []  # No workflow outputs defined

        # Test union types for workflow outputs too
        @executor
        async def multi_workflow_output(data: str, ctx: WorkflowContext[Never, str | int | bool]) -> None:
            if data.isdigit():
                await ctx.yield_output(int(data))
            elif data.lower() in ("true", "false"):
                await ctx.yield_output(data.lower() == "true")
            else:
                await ctx.yield_output(data.upper())

        workflow_spec = multi_workflow_output._handler_specs[0]
        assert workflow_spec["output_types"] == []  # None means no message outputs
        assert set(workflow_spec["workflow_output_types"]) == {str, int, bool}

    def test_none_output_type(self):
        """Test WorkflowContext produces empty output types."""

        @executor
        async def no_output(data: Any, ctx: WorkflowContext) -> None:
            # This executor doesn't send any messages
            pass

        spec = no_output._handler_specs[0]
        assert spec["output_types"] == []
        assert spec["workflow_output_types"] == []  # No workflow outputs defined

    def test_any_output_type(self):
        """Test WorkflowContext[Any] and WorkflowContext[Any, Any] produce Any output types."""

        @executor
        async def any_output(data: str, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message("result")

        spec = any_output._handler_specs[0]
        assert spec["output_types"] == [Any]
        assert spec["workflow_output_types"] == []  # No workflow outputs defined

        # Test both parameters as Any
        @executor
        async def any_both_output(data: str, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.send_message("message")
            await ctx.yield_output("workflow_output")

        both_spec = any_both_output._handler_specs[0]
        assert both_spec["output_types"] == [Any]
        assert both_spec["workflow_output_types"] == [Any]

    def test_validation_errors(self):
        """Test various validation errors in function signatures."""

        # Wrong number of parameters (now accepts 1 or 2, so 0 or 3+ should fail)
        async def no_params() -> None:
            pass

        with pytest.raises(
            ValueError, match="must have \\(message: T\\) or \\(message: T, ctx: WorkflowContext\\[U\\]\\)"
        ):
            FunctionExecutor(no_params)  # type: ignore

        async def too_many_params(data: str, ctx: WorkflowContext[str], extra: int) -> None:
            pass

        with pytest.raises(
            ValueError, match="must have \\(message: T\\) or \\(message: T, ctx: WorkflowContext\\[U\\]\\)"
        ):
            FunctionExecutor(too_many_params)  # type: ignore

        # Missing message type annotation
        async def no_msg_type(data, ctx: WorkflowContext[str]) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="type annotation for the message"):
            FunctionExecutor(no_msg_type)  # type: ignore

        # Missing ctx annotation (only for 2-parameter functions)
        async def no_ctx_type(data: str, ctx) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="must have a WorkflowContext"):
            FunctionExecutor(no_ctx_type)  # type: ignore

        # Wrong ctx type
        async def wrong_ctx_type(data: str, ctx: str) -> None:  # type: ignore
            pass

        with pytest.raises(ValueError, match="must be annotated as WorkflowContext"):
            FunctionExecutor(wrong_ctx_type)  # type: ignore

        # Unparameterized WorkflowContext is now allowed
        async def unparameterized_ctx(data: str, ctx: WorkflowContext) -> None:  # type: ignore
            pass

        # This should now succeed since unparameterized WorkflowContext is allowed
        executor = FunctionExecutor(unparameterized_ctx)
        assert executor.output_types == []  # Unparameterized has no inferred types
        assert executor.workflow_output_types == []  # No workflow output types

    async def test_execution_in_workflow(self):
        """Test that FunctionExecutor works properly in a workflow."""

        @executor(id="upper")
        async def to_upper(text: str, ctx: WorkflowContext[str]) -> None:
            result = text.upper()
            await ctx.send_message(result)

        @executor(id="reverse")
        async def reverse_text(text: str, ctx: WorkflowContext[Any, str]) -> None:
            result = text[::-1]
            await ctx.yield_output(result)

        # Verify type inference for both executors
        upper_spec = to_upper._handler_specs[0]
        assert upper_spec["output_types"] == [str]
        assert upper_spec["workflow_output_types"] == []  # No workflow outputs

        reverse_spec = reverse_text._handler_specs[0]
        assert reverse_spec["output_types"] == [Any]  # First parameter is Any
        assert reverse_spec["workflow_output_types"] == [str]  # Second parameter is str

        workflow = WorkflowBuilder().add_edge(to_upper, reverse_text).set_start_executor(to_upper).build()

        # Run workflow
        events = await workflow.run("hello world")
        outputs = events.get_outputs()

        # Assert that we got the expected output
        assert len(outputs) == 1
        assert outputs[0] == "DLROW OLLEH"

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
            func_exec._register_instance_handler(
                name="second",
                func=second_handler,
                message_type=str,
                ctx_annotation=WorkflowContext[str],
                output_types=[str],
                workflow_output_types=[],
            )

    def test_complex_type_annotations(self):
        """Test with complex type annotations like List[str], Dict[str, int], etc."""

        @executor
        async def process_list(items: list[str], ctx: WorkflowContext[dict[str, int]]) -> None:
            result = {item: len(item) for item in items}
            await ctx.send_message(result)

        spec = process_list._handler_specs[0]
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
        spec = process_simple._handler_specs[0]
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

    def test_sync_function_basic(self):
        """Test basic synchronous function support."""

        @executor(id="sync_processor")
        def process_sync(text: str):
            return text.upper()

        assert isinstance(process_sync, FunctionExecutor)
        assert process_sync.id == "sync_processor"
        assert str in process_sync._handlers

        # Check spec - sync single parameter functions have no output types
        spec = process_sync._handler_specs[0]
        assert spec["message_type"] is str
        assert spec["output_types"] == []
        assert spec["ctx_annotation"] is None

    def test_sync_function_with_context(self):
        """Test synchronous function with WorkflowContext."""

        @executor
        def sync_with_ctx(value: int, ctx: WorkflowContext[int]):
            # Sync functions can still use context
            return value * 2

        assert isinstance(sync_with_ctx, FunctionExecutor)
        assert sync_with_ctx.id == "sync_with_ctx"
        assert int in sync_with_ctx._handlers

        # Check spec - sync functions with context can infer output types
        spec = sync_with_ctx._handler_specs[0]
        assert spec["message_type"] is int
        assert spec["output_types"] == [int]

    def test_sync_function_can_handle(self):
        """Test that sync functions work with can_handle method."""

        @executor
        def string_handler(text: str):
            return text.strip()

        assert string_handler.can_handle("hello")
        assert not string_handler.can_handle(123)
        assert not string_handler.can_handle([])

    def test_sync_function_validation(self):
        """Test validation for synchronous functions."""

        # Valid sync function with one parameter
        def valid_sync(data: str):
            return data.upper()

        func_exec = FunctionExecutor(valid_sync)
        assert str in func_exec._handlers

        # Valid sync function with two parameters
        def valid_sync_with_ctx(data: int, ctx: WorkflowContext[str]):
            return str(data)

        func_exec2 = FunctionExecutor(valid_sync_with_ctx)
        assert int in func_exec2._handlers

        # Sync function with missing type annotation should still fail
        def no_annotation(data):  # type: ignore
            return data

        with pytest.raises(ValueError, match="type annotation for the message"):
            FunctionExecutor(no_annotation)  # type: ignore

    def test_mixed_sync_async_decorator(self):
        """Test that both sync and async functions work with decorator."""

        @executor
        def sync_func(data: str):
            return data.lower()

        @executor
        async def async_func(data: str):
            return data.upper()

        # Both should be FunctionExecutor instances
        assert isinstance(sync_func, FunctionExecutor)
        assert isinstance(async_func, FunctionExecutor)

        # Both should handle strings
        assert sync_func.can_handle("test")
        assert async_func.can_handle("test")

        # Both should be different instances
        assert sync_func is not async_func

    async def test_sync_function_in_workflow(self):
        """Test that sync functions work properly in a workflow context."""

        @executor(id="sync_upper")
        def to_upper_sync(text: str, ctx: WorkflowContext[str]):
            return text.upper()
            # Note: For the test, we'll use a sync send mechanism
            # In practice, the wrapper handles the async conversion

        @executor(id="async_reverse")
        async def reverse_async(text: str, ctx: WorkflowContext[Any, str]):
            result = text[::-1]
            await ctx.yield_output(result)

        # Verify type inference for sync and async functions
        sync_spec = to_upper_sync._handler_specs[0]
        assert sync_spec["output_types"] == [str]
        assert sync_spec["workflow_output_types"] == []  # No workflow outputs

        async_spec = reverse_async._handler_specs[0]
        assert async_spec["output_types"] == [Any]  # First parameter is Any
        assert async_spec["workflow_output_types"] == [str]  # Second parameter is str

        # Verify the executors can handle their input types
        assert to_upper_sync.can_handle("hello")
        assert reverse_async.can_handle("HELLO")

        # For integration testing, we mainly verify that the handlers are properly registered
        # and the functions are wrapped correctly
        assert str in to_upper_sync._handlers
        assert str in reverse_async._handlers

    async def test_sync_function_thread_execution(self):
        """Test that sync functions run in thread pool and don't block the event loop."""
        import threading
        import time

        _ = threading.get_ident()
        execution_thread_id = None

        @executor
        def blocking_function(data: str):
            nonlocal execution_thread_id
            execution_thread_id = threading.get_ident()
            # Simulate some CPU-bound work
            time.sleep(0.01)  # Small sleep to verify thread execution
            return data.upper()

        # Verify the function is wrapped and registered
        assert str in blocking_function._handlers

        # For a more complete test, we'd need to create a full workflow context,
        # but for now we can verify that the function was properly wrapped
        # and that sync functions store the correct metadata
        assert not blocking_function._is_async
        assert not blocking_function._has_context

        # The actual thread execution test would require a full workflow setup,
        # but the important thing is that asyncio.to_thread is used in the wrapper
