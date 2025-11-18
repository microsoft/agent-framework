# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any

from agent_framework import FunctionExecutor, WorkflowContext, executor


class TestFunctionExecutorFutureAnnotations:
    """Test suite for FunctionExecutor with from __future__ import annotations."""

    def test_executor_decorator_future_annotations(self):
        """Test @executor decorator works with stringified annotations."""

        @executor(id="future_test")
        async def process_future(value: int, ctx: WorkflowContext[int]) -> None:
            await ctx.send_message(value * 2)

        assert isinstance(process_future, FunctionExecutor)
        assert process_future.id == "future_test"
        assert int in process_future._handlers

        # Check spec
        spec = process_future._handler_specs[0]
        assert spec["message_type"] is int
        assert spec["output_types"] == [int]

    def test_executor_decorator_future_annotations_complex(self):
        """Test @executor decorator works with complex stringified annotations."""

        @executor
        async def process_complex(data: dict[str, Any], ctx: WorkflowContext[list[str]]) -> None:
            await ctx.send_message(["done"])

        assert isinstance(process_complex, FunctionExecutor)
        spec = process_complex._handler_specs[0]
        assert spec["message_type"] == dict[str, Any]
        assert spec["output_types"] == [list[str]]
