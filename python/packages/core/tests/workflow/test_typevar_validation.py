# Copyright (c) Microsoft. All rights reserved.

"""Tests for unresolved TypeVar detection during handler/executor registration."""

from typing import TypeVar

import pytest
from typing_extensions import Never

from agent_framework import (
    Executor,
    FunctionExecutor,
    WorkflowContext,
    executor,
    handler,
)
from agent_framework._workflows._typing_utils import is_typevar

T = TypeVar("T")
U = TypeVar("U")


class TestIsTypevarHelper:
    """Tests for the runtime-safe is_typevar helper."""

    def test_detects_typing_typevar(self):
        """is_typevar should detect TypeVar from typing module."""
        import typing

        tv = typing.TypeVar("tv")
        assert is_typevar(tv)

    def test_detects_typing_extensions_typevar(self):
        """is_typevar should detect TypeVar from typing_extensions module."""
        import typing_extensions

        tv = typing_extensions.TypeVar("tv")
        assert is_typevar(tv)

    def test_rejects_concrete_types(self):
        """is_typevar should return False for concrete types."""
        assert not is_typevar(str)
        assert not is_typevar(int)
        assert not is_typevar(None)
        assert not is_typevar(Never)

    def test_rejects_non_types(self):
        """is_typevar should return False for non-type values."""
        assert not is_typevar("hello")
        assert not is_typevar(42)
        assert not is_typevar([])


class TestHandlerTypeVarValidation:
    """Tests for @handler decorator rejecting unresolved TypeVars."""

    def test_handler_explicit_input_typevar_raises(self):
        """@handler(input=T) with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            class _Bad(Executor):  # pyright: ignore[reportUnusedClass]
                @handler(input=T)  # type: ignore[arg-type]
                async def handle(self, message, ctx: WorkflowContext[str]) -> None:  # type: ignore[no-untyped-def]
                    pass

    def test_handler_explicit_output_typevar_raises(self):
        """@handler(input=str, output=T) with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            class _Bad(Executor):  # pyright: ignore[reportUnusedClass]
                @handler(input=str, output=T)  # type: ignore[arg-type]
                async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
                    pass

    def test_handler_explicit_workflow_output_typevar_raises(self):
        """@handler(input=str, workflow_output=T) should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            class _Bad(Executor):  # pyright: ignore[reportUnusedClass]
                @handler(input=str, workflow_output=T)  # type: ignore[arg-type]
                async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
                    pass

    def test_handler_introspected_typevar_raises(self):
        """@handler with TypeVar in message annotation should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            class _Bad(Executor):  # pyright: ignore[reportUnusedClass]
                @handler  # type: ignore[arg-type]
                async def handle(self, message: T, ctx: WorkflowContext[str]) -> None:  # type: ignore[valid-type]
                    pass

    def test_handler_concrete_types_work(self):
        """@handler with concrete types should succeed."""

        class Good(Executor):
            @handler(input=str, output=str)
            async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
                pass

        assert Good is not None


class TestExecutorTypeVarValidation:
    """Tests for @executor decorator rejecting unresolved TypeVars."""

    def test_executor_explicit_input_typevar_raises(self):
        """@executor(input=T) with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            @executor(input=T)  # type: ignore[arg-type]
            async def bad_func(message, ctx: WorkflowContext[str]) -> None:  # type: ignore[no-untyped-def]
                pass

    def test_executor_explicit_output_typevar_raises(self):
        """@executor(input=str, output=T) with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            @executor(input=str, output=T)  # type: ignore[arg-type]
            async def bad_func(message: str, ctx: WorkflowContext[str]) -> None:
                pass

    def test_executor_introspected_typevar_raises(self):
        """@executor with TypeVar in message annotation should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):
            FunctionExecutor(self._make_typevar_func())  # type: ignore[arg-type]

    def test_executor_concrete_types_work(self):
        """@executor with concrete types should succeed."""

        @executor(input=str, output=str)
        async def good_func(message: str, ctx: WorkflowContext[str]) -> None:
            pass

        assert good_func is not None

    @staticmethod
    def _make_typevar_func():
        """Create a function with TypeVar annotation for testing."""

        async def func(message: T, ctx: WorkflowContext[str]) -> None:  # type: ignore[valid-type]
            pass

        return func


class TestWorkflowContextTypeVarValidation:
    """Tests for WorkflowContext[T] rejecting unresolved TypeVars."""

    def test_context_direct_typevar_raises(self):
        """WorkflowContext[T] with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            @executor(id="bad")
            async def bad_func(message: str, ctx: WorkflowContext[T]) -> None:  # type: ignore[valid-type]
                pass

    def test_context_union_typevar_raises(self):
        """WorkflowContext[T | str] with a TypeVar in union should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            @executor(id="bad")
            async def bad_func(message: str, ctx: WorkflowContext[T | str]) -> None:  # type: ignore[valid-type]
                pass

    def test_context_workflow_output_typevar_raises(self):
        """WorkflowContext[str, T] with a TypeVar should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            @executor(id="bad")
            async def bad_func(message: str, ctx: WorkflowContext[str, T]) -> None:  # type: ignore[valid-type]
                pass

    def test_context_concrete_types_work(self):
        """WorkflowContext[str] with concrete types should succeed."""

        @executor(id="good")
        async def good_func(message: str, ctx: WorkflowContext[str]) -> None:
            pass

        assert good_func is not None

    def test_context_class_handler_typevar_raises(self):
        """Class-based handler with WorkflowContext[T] should raise ValueError."""
        with pytest.raises(ValueError, match="unresolved TypeVar"):

            class _Bad(Executor):  # pyright: ignore[reportUnusedClass]
                @handler  # pyright: ignore[reportUnknownArgumentType]
                async def handle(self, message: str, ctx: WorkflowContext[T]) -> None:  # type: ignore[valid-type]
                    pass
