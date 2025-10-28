# Copyright (c) Microsoft. All rights reserved.

"""Function-based Executor and decorator utilities.

This module provides:
- FunctionExecutor: an Executor subclass that wraps a standalone user-defined function
  with signature (message) or (message, ctx: WorkflowContext[T]). Both sync and async functions are supported.
  Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid blocking the event loop.
- executor decorator: converts a standalone module-level function into a ready-to-use Executor instance
  with proper type validation and handler registration.

Design Pattern:
  - Use @executor for standalone module-level or local functions
  - Use Executor subclass with @handler for class-based executors with state/dependencies
  - Do NOT use @executor with @staticmethod or @classmethod
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, overload

from ._executor import Executor
from ._workflow_context import WorkflowContext, validate_function_signature


class FunctionExecutor(Executor):
    """Executor that wraps a user-defined function.

    This executor allows users to define simple functions (both sync and async) and use them
    as workflow executors without needing to create full executor classes.

    Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid
    blocking the event loop.
    """

    @staticmethod
    def _validate_function(func: Callable[..., Any]) -> tuple[type, Any, list[type[Any]], list[type[Any]]]:
        """Validate that the function has the correct signature for an executor.

        Args:
            func: The function to validate (can be sync or async)

        Returns:
            Tuple of (message_type, ctx_annotation, output_types, workflow_output_types)

        Raises:
            ValueError: If the function signature is incorrect
        """
        return validate_function_signature(func, "Function")

    def __init__(self, func: Callable[..., Any], id: str | None = None):
        """Initialize the FunctionExecutor with a user-defined function.

        Args:
            func: The function to wrap as an executor (can be sync or async)
            id: Optional executor ID. If None, uses the function name.

        Raises:
            ValueError: If func is a staticmethod or classmethod (use @handler on instance methods instead)
        """
        # Detect misuse of @executor with staticmethod/classmethod
        if isinstance(func, (staticmethod, classmethod)):
            descriptor_type = "staticmethod" if isinstance(func, staticmethod) else "classmethod"
            raise ValueError(
                f"The @executor decorator cannot be used with @{descriptor_type}. "
                f"Use the @executor decorator on standalone module-level functions, "
                f"or create an Executor subclass and use @handler on instance methods instead."
            )

        # Validate function signature and extract types
        message_type, ctx_annotation, output_types, workflow_output_types = self._validate_function(func)

        # Determine if function has WorkflowContext parameter
        has_context = ctx_annotation is not None

        # Check if function is async
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


@overload
def executor(func: Callable[..., Any]) -> FunctionExecutor: ...


@overload
def executor(*, id: str | None = None) -> Callable[[Callable[..., Any]], FunctionExecutor]: ...


def executor(
    func: Callable[..., Any] | None = None, *, id: str | None = None
) -> Callable[[Callable[..., Any]], FunctionExecutor] | FunctionExecutor:
    """Decorator that converts a standalone function into a FunctionExecutor instance.

    The @executor decorator is designed for **standalone module-level functions only**.
    For class-based executors, use the Executor base class with @handler on instance methods.

    Supports both synchronous and asynchronous functions. Synchronous functions
    are executed in a thread pool to avoid blocking the event loop.

    Important:
        - Use @executor for standalone functions (module-level or local functions)
        - Do NOT use @executor with @staticmethod or @classmethod
        - For class-based executors, subclass Executor and use @handler on instance methods

    Usage:

    .. code-block:: python

        # Standalone async function (RECOMMENDED):
        @executor(id="upper_case")
        async def to_upper(text: str, ctx: WorkflowContext[str]):
            await ctx.send_message(text.upper())


        # Standalone sync function (runs in thread pool):
        @executor
        def process_data(data: str):
            return data.upper()


        # For class-based executors, use @handler instead:
        class MyExecutor(Executor):
            def __init__(self):
                super().__init__(id="my_executor")

            @handler
            async def process(self, data: str, ctx: WorkflowContext[str]):
                await ctx.send_message(data.upper())

    Args:
        func: The function to decorate (when used without parentheses)
        id: Optional custom ID for the executor. If None, uses the function name.

    Returns:
        A FunctionExecutor instance that can be wired into a Workflow.

    Raises:
        ValueError: If used with @staticmethod or @classmethod (unsupported pattern)
    """

    def wrapper(func: Callable[..., Any]) -> FunctionExecutor:
        return FunctionExecutor(func, id=id)

    # If func is provided, this means @executor was used without parentheses
    if func is not None:
        return wrapper(func)

    # Otherwise, return the wrapper for @executor() or @executor(id="...")
    return wrapper
