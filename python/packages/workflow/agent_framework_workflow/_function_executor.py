# Copyright (c) Microsoft. All rights reserved.

"""Function-based Executor and decorator utilities.

This module provides:
- FunctionExecutor: an Executor subclass that wraps a user-defined async function
  with signature (message, ctx: WorkflowContext[T]).
- executor decorator: converts such a function into a ready-to-use Executor instance
  with proper type validation and handler registration.
"""

from __future__ import annotations

import asyncio
import inspect
from types import UnionType
from typing import Any, Awaitable, Callable, Union, get_args, get_origin

from ._executor import Executor
from ._workflow_context import WorkflowContext


def _is_workflow_context_type(annotation: Any) -> bool:
    """Check if an annotation represents WorkflowContext[T]."""
    origin = get_origin(annotation)
    if origin is WorkflowContext:
        return True
    # Also handle the case where the raw WorkflowContext class is used
    return annotation is WorkflowContext


def _infer_output_types_from_ctx_annotation(ctx_annotation: Any) -> list[type]:
    """Infer output types list from the WorkflowContext generic parameter.

    Examples:
    - WorkflowContext[str] -> [str]
    - WorkflowContext[str | int] -> [str, int]
    - WorkflowContext[Union[str, int]] -> [str, int]
    - WorkflowContext[Any] -> [] (unknown)
    - WorkflowContext[None] -> []
    """
    # If no annotation or not parameterized, return empty list
    try:
        origin = get_origin(ctx_annotation)
    except Exception:
        origin = None

    # If annotation is unsubscripted WorkflowContext, nothing to infer
    if origin is None:
        return []

    # Expecting WorkflowContext[T]
    if origin is not WorkflowContext:
        return []

    args = get_args(ctx_annotation)
    if not args:
        return []

    t = args[0]
    # If t is a Union, flatten it
    t_origin = get_origin(t)
    # If Any, treat as unknown -> no output types inferred
    if t is Any:
        return []

    if t_origin in (Union, UnionType):
        # Return all union args as-is (may include generic aliases like list[str])
        return [arg for arg in get_args(t) if arg is not Any and arg is not type(None)]

    # Single concrete or generic alias type (e.g., str, int, list[str])
    if t is Any or t is type(None):
        return []
    return [t]


def _validate_function_signature(func: Callable[..., Any]) -> tuple[type, Any]:
    """Validate the function signature and return (message_type, ctx_annotation).

    Requirements:
    - async function
    - exactly two parameters: (message, ctx)
    - message parameter must have a type annotation
    - ctx must be annotated as WorkflowContext[TOut]
    """
    if not inspect.iscoroutinefunction(func):
        raise TypeError("@executor expects an async function (use 'async def').")

    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if len(params) != 2:
        raise ValueError("@executor functions must have exactly two parameters: (message, ctx).")

    msg_param = params[0]
    ctx_param = params[1]

    if msg_param.annotation is inspect.Parameter.empty:
        raise ValueError("@executor function's first parameter must have a type annotation for the message.")

    message_type = msg_param.annotation

    if ctx_param.annotation is inspect.Parameter.empty:
        raise ValueError("@executor function's second parameter must be annotated as WorkflowContext[T].")

    ctx_ann = ctx_param.annotation
    origin = get_origin(ctx_ann)
    # Allow unsubscripted WorkflowContext to be flagged here for clarity
    if origin is None:
        if ctx_ann is WorkflowContext:
            raise ValueError(
                "@executor requires WorkflowContext[T] with a concrete T (use WorkflowContext[None] if no outputs)."
            )
        raise ValueError(f"@executor function ctx parameter must be WorkflowContext[T], got {ctx_ann}.")

    if origin is not WorkflowContext:
        raise ValueError(f"@executor function ctx parameter must be WorkflowContext[T], got {ctx_ann}.")

    # Ensure T is provided (could be Any/None/Union, validator downstream handles semantics)
    t_args = get_args(ctx_ann)
    if not t_args:
        raise ValueError(
            "@executor requires WorkflowContext[T] with a concrete T (use WorkflowContext[None] if no outputs)."
        )

    return message_type, ctx_ann


class FunctionExecutor(Executor):
    """Executor that wraps a user-defined function.

    This executor allows users to define simple async functions and use them
    as workflow executors without needing to create full executor classes.
    """

    @staticmethod
    def _validate_function(func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]]) -> None:
        """Validate that the function has the correct signature for an executor.

        Args:
            func: The function to validate

        Raises:
            TypeError: If the function is not async
            ValueError: If the function signature is incorrect
        """
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("@executor expects an async function")

        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        if len(params) != 2:
            raise ValueError(
                f"Function {func.__name__} must have exactly two parameters: "
                f"(message: T, ctx: WorkflowContext[U]). Got {len(params)} parameters."
            )

        message_param, ctx_param = params

        # Check message parameter has type annotation
        if message_param.annotation == inspect.Parameter.empty:
            raise ValueError(f"Function {func.__name__} must have a type annotation for the message parameter")

        # Check ctx parameter has proper type annotation
        if ctx_param.annotation == inspect.Parameter.empty:
            raise ValueError(f"Function {func.__name__} second parameter must be annotated as WorkflowContext[T]")

        # Validate that ctx parameter is WorkflowContext[T]
        if not _is_workflow_context_type(ctx_param.annotation):
            raise ValueError(
                f"Function {func.__name__} second parameter must be annotated as WorkflowContext[T], "
                f"got {ctx_param.annotation}"
            )

        # Check that WorkflowContext has a concrete type parameter
        if ctx_param.annotation is WorkflowContext:
            # This is unparameterized WorkflowContext
            raise ValueError(
                f"Function {func.__name__} WorkflowContext must be parameterized with a concrete T. "
                f"Use WorkflowContext[str], WorkflowContext[int], etc."
            )

        if hasattr(ctx_param.annotation, "__args__") and ctx_param.annotation.__args__:
            # This is WorkflowContext[T] with a concrete T
            pass
        else:
            raise ValueError(
                f"Function {func.__name__} WorkflowContext must be parameterized with a concrete T. "
                f"Use WorkflowContext[str], WorkflowContext[int], etc."
            )

    def __init__(self, func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]], id: str | None = None):
        """Initialize the FunctionExecutor with a user-defined function.

        Args:
            func: The async function to wrap as an executor
            id: Optional executor ID. If None, uses the function name.
        """
        # Validate function signature first
        self._validate_function(func)

        # Extract types from function signature
        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        message_type = params[0].annotation
        ctx_annotation = params[1].annotation
        output_types = _infer_output_types_from_ctx_annotation(ctx_annotation)

        # Initialize parent WITHOUT calling _discover_handlers yet
        # We'll manually set up the attributes first
        executor_id = id or getattr(func, "__name__", "FunctionExecutor")
        kwargs = {"id": executor_id, "type": "FunctionExecutor"}

        # Set up the base class attributes manually to avoid _discover_handlers
        from pydantic import BaseModel

        BaseModel.__init__(self, **kwargs)

        self._handlers: dict[type, Callable[[Any, WorkflowContext[Any]], Any]] = {}
        self._request_interceptors: dict[type | str, list[dict[str, Any]]] = {}
        self._instance_handler_specs: list[dict[str, Any]] = []

        # Now register our instance handler
        self.register_instance_handler(
            name=func.__name__,
            func=func,
            message_type=message_type,
            ctx_annotation=ctx_annotation,
            output_types=output_types,
        )

        # Now we can safely call _discover_handlers (it won't find any class-level handlers)
        self._discover_handlers()


def executor(
    *, id: str | None = None
) -> Callable[[Callable[[Any, WorkflowContext[Any]], Awaitable[Any]]], FunctionExecutor]:
    """Decorator that converts an async function into a FunctionExecutor instance.

    Usage:
        @executor(id="upper_case")
        async def to_upper(text: str, ctx: WorkflowContext[str]):
            await ctx.send_message(text.upper())

    Returns an Executor instance that can be wired into a WorkflowBuilder.
    """

    def wrapper(func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]]) -> FunctionExecutor:
        return FunctionExecutor(func, id=id)

    return wrapper
