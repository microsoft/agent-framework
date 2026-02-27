# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from agent_framework import Executor, WorkflowContext, handler


class MyTypeA(BaseModel):
    pass


class MyTypeB(BaseModel):
    pass


class MyTypeC(BaseModel):
    pass


class TestExecutorFutureAnnotations:
    """Test suite for Executor with from __future__ import annotations."""

    def test_handler_decorator_future_annotations(self):
        """Test @handler decorator works with stringified annotations (issue #3898)."""

        class MyExecutor(Executor):
            @handler
            async def example(self, input: str, ctx: WorkflowContext[MyTypeA, MyTypeB]) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        assert str in exec_instance._handlers
        spec = exec_instance._handler_specs[0]
        assert spec["message_type"] is str
        assert spec["output_types"] == [MyTypeA]
        assert spec["workflow_output_types"] == [MyTypeB]

    def test_handler_decorator_future_annotations_single_type_arg(self):
        """Test @handler with single type argument and future annotations."""

        class MyExecutor(Executor):
            @handler
            async def example(self, input: int, ctx: WorkflowContext[MyTypeA]) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        assert int in exec_instance._handlers
        spec = exec_instance._handler_specs[0]
        assert spec["message_type"] is int
        assert spec["output_types"] == [MyTypeA]

    def test_handler_decorator_future_annotations_complex(self):
        """Test @handler with complex type annotations and future annotations."""

        class MyExecutor(Executor):
            @handler
            async def example(self, data: dict[str, Any], ctx: WorkflowContext[list[str]]) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        spec = exec_instance._handler_specs[0]
        assert spec["message_type"] == dict[str, Any]
        assert spec["output_types"] == [list[str]]

    def test_handler_decorator_future_annotations_bare_context(self):
        """Test @handler with bare WorkflowContext and future annotations."""

        class MyExecutor(Executor):
            @handler
            async def example(self, input: str, ctx: WorkflowContext) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        assert str in exec_instance._handlers
        spec = exec_instance._handler_specs[0]
        assert spec["output_types"] == []
        assert spec["workflow_output_types"] == []

    def test_handler_decorator_future_annotations_explicit_types(self):
        """Test @handler with explicit type parameters under future annotations."""

        class MyExecutor(Executor):
            @handler(input=str, output=MyTypeA)
            async def example(self, input, ctx) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        assert str in exec_instance._handlers
        spec = exec_instance._handler_specs[0]
        assert spec["message_type"] is str
        assert spec["output_types"] == [MyTypeA]

    def test_handler_decorator_future_annotations_union_context(self):
        """Test @handler with union type context annotations and future annotations."""

        class MyExecutor(Executor):
            @handler
            async def example(self, input: str, ctx: WorkflowContext[MyTypeA | MyTypeB, MyTypeC]) -> None:
                pass

        exec_instance = MyExecutor(id="test")
        assert str in exec_instance._handlers
        spec = exec_instance._handler_specs[0]
        assert spec["output_types"] == [MyTypeA, MyTypeB]
        assert spec["workflow_output_types"] == [MyTypeC]

    def test_handler_unresolvable_annotation_raises(self):
        """Test that an unresolvable forward-reference annotation raises ValueError.

        When get_type_hints fails (e.g. NameError for NonExistentType), the code falls back
        to raw string annotations. The ctx parameter's raw string annotation is then not
        recognised as a valid WorkflowContext type, so a ValueError is still raised.
        """
        with pytest.raises(ValueError):

            class Bad(Executor):
                @handler
                async def example(self, input: NonExistentType, ctx: WorkflowContext[MyTypeA, MyTypeB]) -> None:  # noqa: F821
                    pass
