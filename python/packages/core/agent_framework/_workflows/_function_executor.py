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
from typing import Any, overload

from ._executor import Executor
from ._workflow_context import WorkflowContext, validate_workflow_context_annotation


class FunctionExecutor(Executor):
    """Executor that wraps a user-defined function.

    This executor allows users to define simple functions (both sync and async) and use them
    as workflow executors without needing to create full executor classes.

    Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid
    blocking the event loop.
    """

    def __init__(self, func: Callable[..., Any], id: str | None = None):
        """Initialize the FunctionExecutor with a user-defined function.

        Args:
            func: The function to wrap as an executor (can be sync or async)
            id: Optional executor ID. If None, uses the function name.
        """
        # Validate function signature and extract types
        message_type, ctx_annotation, output_types, workflow_output_types = _validate_function_signature(func)

        # Determine if function has WorkflowContext parameter
        has_context = ctx_annotation is not None
        is_async = asyncio.iscoroutinefunction(func)

        # Initialize parent WITHOUT calling _discover_handlers yet
        # We'll manually set up the attributes first
        executor_id = str(id or getattr(func, "__name__", "FunctionExecutor"))
        kwargs = {"type": "FunctionExecutor"}

        super().__init__(id=executor_id, defer_discovery=True, **kwargs)
        self._handlers = {}
        self._handler_specs = []

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
        self._register_instance_handler(
            name=func.__name__,
            func=wrapped_func,
            message_type=message_type,
            ctx_annotation=ctx_annotation,
            output_types=output_types,
            workflow_output_types=workflow_output_types,
        )

        # Now we can safely call _discover_handlers (it won't find any class-level handlers)
        self._discover_handlers()

        if not self._handlers:
            raise ValueError(
                f"FunctionExecutor {self.__class__.__name__} failed to register handler for {func.__name__}"
            )


# region Decorator


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


# endregion: Decorator

# region Function Validation


def _validate_function_signature(func: Callable[..., Any]) -> tuple[type, Any, list[type[Any]], list[type[Any]]]:
    """Validate function signature for executor functions.

    Args:
        func: The function to validate

    Returns:
        Tuple of (message_type, ctx_annotation, output_types, workflow_output_types)

    Raises:
        ValueError: If the function signature is invalid
    """
    signature = inspect.signature(func)
    params = list(signature.parameters.values())

    expected_counts = (1, 2)  # Function executor: (message) or (message, ctx)
    param_description = "(message: T) or (message: T, ctx: WorkflowContext[U])"
    if len(params) not in expected_counts:
        raise ValueError(
            f"Function instance {func.__name__} must have {param_description}. Got {len(params)} parameters."
        )

    # Check message parameter has type annotation
    message_param = params[0]
    if message_param.annotation == inspect.Parameter.empty:
        raise ValueError(f"Function instance {func.__name__} must have a type annotation for the message parameter")

    message_type = message_param.annotation

    # Check if there's a context parameter
    if len(params) == 2:
        ctx_param = params[1]
        output_types, workflow_output_types = validate_workflow_context_annotation(
            ctx_param.annotation, f"parameter '{ctx_param.name}'", "Function instance"
        )
        ctx_annotation = ctx_param.annotation
    else:
        # No context parameter (only valid for function executors)
        output_types, workflow_output_types = [], []
        ctx_annotation = None

    return message_type, ctx_annotation, output_types, workflow_output_types


# endregion: Function Validation
