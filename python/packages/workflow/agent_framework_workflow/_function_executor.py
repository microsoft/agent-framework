# Copyright (c) Microsoft. All rights reserved.

"""Function-based Executor and decorator utilities.

This module provides:
- FunctionExecutor: an Executor subclass that wraps a user-defined function
  with signature (message) or (message, ctx: WorkflowContext[T]). Both sync and async functions are supported.
  Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid blocking the event loop.
- executor decorator: converts such a function into a ready-to-use Executor instance
  with proper type validation and handler registration.
"""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from types import UnionType
from typing import Any, Union, get_args, get_origin, overload

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


class FunctionExecutor(Executor):
    """Executor that wraps a user-defined function.

    This executor allows users to define simple functions (both sync and async) and use them
    as workflow executors without needing to create full executor classes.

    Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid
    blocking the event loop.
    """

    @staticmethod
    def _validate_function(func: Callable[..., Any]) -> None:
        """Validate that the function has the correct signature for an executor.

        Args:
            func: The function to validate (can be sync or async)

        Raises:
            ValueError: If the function signature is incorrect
        """
        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        if len(params) not in (1, 2):
            raise ValueError(
                f"Function {func.__name__} must have one or two parameters: "
                f"(message: T) or (message: T, ctx: WorkflowContext[U]). Got {len(params)} parameters."
            )

        message_param = params[0]

        # Check message parameter has type annotation
        if message_param.annotation == inspect.Parameter.empty:
            raise ValueError(f"Function {func.__name__} must have a type annotation for the message parameter")

        # If there's a second parameter, validate it's WorkflowContext[T]
        if len(params) == 2:
            ctx_param = params[1]

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

    def __init__(self, func: Callable[..., Any], id: str | None = None):
        """Initialize the FunctionExecutor with a user-defined function.

        Args:
            func: The function to wrap as an executor (can be sync or async)
            id: Optional executor ID. If None, uses the function name.
        """
        # Validate function signature first
        self._validate_function(func)

        # Extract types from function signature
        signature = inspect.signature(func)
        params = list(signature.parameters.values())

        message_type = params[0].annotation

        # Determine if function has WorkflowContext parameter
        has_context = len(params) == 2
        is_async = asyncio.iscoroutinefunction(func)

        if has_context:
            ctx_annotation = params[1].annotation
            output_types = _infer_output_types_from_ctx_annotation(ctx_annotation)
        else:
            # For single-parameter functions, we can't infer output types
            ctx_annotation = None
            output_types = []

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

        # Store the original function and whether it has context
        self._original_func = func
        self._has_context = has_context
        self._is_async = is_async

        # Create a wrapper function that always accepts both message and context
        if has_context and is_async:
            # Async function with context - already has the right signature
            wrapped_func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]] = func  # type: ignore
        elif has_context and not is_async:
            # Sync function with context - wrap to make async using thread pool
            async def wrapped_func(message: Any, ctx: WorkflowContext[Any]) -> Any:
                # Call the sync function with both parameters in a thread
                return await asyncio.to_thread(func, message, ctx)  # type: ignore

        elif not has_context and is_async:
            # Async function without context - wrap to ignore context
            async def wrapped_func(message: Any, ctx: WorkflowContext[Any]) -> Any:
                # Call the async function with just the message
                return await func(message)  # type: ignore

        else:
            # Sync function without context - wrap to make async and ignore context using thread pool
            async def wrapped_func(message: Any, ctx: WorkflowContext[Any]) -> Any:
                # Call the sync function with just the message in a thread
                return await asyncio.to_thread(func, message)  # type: ignore

        # Now register our instance handler
        self.register_instance_handler(
            name=func.__name__,
            func=wrapped_func,
            message_type=message_type,
            ctx_annotation=ctx_annotation,
            output_types=output_types,
        )

        # Now we can safely call _discover_handlers (it won't find any class-level handlers)
        self._discover_handlers()


@overload
def executor(func: Callable[..., Any]) -> FunctionExecutor: ...


@overload
def executor(*, id: str | None = None) -> Callable[[Callable[..., Any]], FunctionExecutor]: ...


def executor(
    func: Callable[..., Any] | None = None, *, id: str | None = None
) -> Callable[[Callable[..., Any]], FunctionExecutor] | FunctionExecutor:
    """Decorator that converts a function into a FunctionExecutor instance.

    Supports both synchronous and asynchronous functions. Synchronous functions
    are executed in a thread pool to avoid blocking the event loop.

    Usage:

    .. code-block:: python

        # With arguments (async function):
        @executor(id="upper_case")
        async def to_upper(text: str, ctx: WorkflowContext[str]):
            await ctx.send_message(text.upper())


        # Without parentheses (sync function - runs in thread pool):
        @executor
        def process_data(data: str):
            # Process data without sending messages
            return data.upper()


        # Sync function with context (runs in thread pool):
        @executor
        def sync_with_context(data: int, ctx: WorkflowContext[int]):
            # Note: sync functions can still use context
            return data * 2

    Returns:
        An Executor instance that can be wired into a Workflow.
    """

    def wrapper(func: Callable[..., Any]) -> FunctionExecutor:
        return FunctionExecutor(func, id=id)

    # If func is provided, this means @executor was used without parentheses
    if func is not None:
        return wrapper(func)

    # Otherwise, return the wrapper for @executor() or @executor(id="...")
    return wrapper
