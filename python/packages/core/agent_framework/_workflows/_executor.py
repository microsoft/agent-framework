# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..observability import create_processing_span
from ._events import (
    ExecutorCompletedEvent,
    ExecutorFailedEvent,
    ExecutorInvokedEvent,
    WorkflowErrorDetails,
    _framework_event_origin,  # type: ignore[reportPrivateUsage]
)
from ._model_utils import DictConvertible
from ._runner_context import Message, RunnerContext  # type: ignore
from ._shared_state import SharedState
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext, validate_function_signature

logger = logging.getLogger(__name__)


# region Executor
class Executor(DictConvertible):
    """Base class for all workflow executors that process messages and perform computations.

    ## Overview
    Executors are the fundamental building blocks of workflows, representing individual processing
    units that receive messages, perform operations, and produce outputs. Each executor is uniquely
    identified and can handle specific message types through decorated handler methods.

    ## Type System
    Executors have a rich type system that defines their capabilities:

    ### Input Types
    The types of messages an executor can process, discovered from handler method signatures:

    .. code-block:: python

        class MyExecutor(Executor):
            @handler
            async def handle_string(self, message: str, ctx: WorkflowContext) -> None:
                # This executor can handle 'str' input types
    Access via the `input_types` property.

    ### Output Types
    The types of messages an executor can send to other executors via `ctx.send_message()`:

    .. code-block:: python

        class MyExecutor(Executor):
            @handler
            async def handle_data(self, message: str, ctx: WorkflowContext[int | bool]) -> None:
                # This executor can send 'int' or 'bool' messages
    Access via the `output_types` property.

    ### Workflow Output Types
    The types of data an executor can emit as workflow-level outputs via `ctx.yield_output()`:

    .. code-block:: python

        class MyExecutor(Executor):
            @handler
            async def process(self, message: str, ctx: WorkflowContext[int, str]) -> None:
                # Can send 'int' messages AND yield 'str' workflow outputs
    Access via the `workflow_output_types` property.

    ## Handler Discovery
    Executors discover their capabilities through decorated methods:

    ### @handler Decorator
    Marks methods that process incoming messages:

    .. code-block:: python

        class MyExecutor(Executor):
            @handler
            async def handle_text(self, message: str, ctx: WorkflowContext[str]) -> None:
                await ctx.send_message(message.upper())

    ### Sub-workflow Request Interception
    Use @handler methods to intercept sub-workflow requests:

    .. code-block:: python

        class ParentExecutor(Executor):
            @handler
            async def handle_domain_request(
                self,
                request: DomainRequest,  # Subclass of RequestInfoMessage
                ctx: WorkflowContext[RequestResponse[RequestInfoMessage, Any] | DomainRequest],
            ) -> None:
                if self.is_allowed(request.domain):
                    response = RequestResponse(data=True, original_request=request, request_id=request.request_id)
                    await ctx.send_message(response, target_id=request.source_executor_id)
                else:
                    await ctx.send_message(request)  # Forward to external

    ## Context Types
    Handler methods receive different WorkflowContext variants based on their type annotations:

    ### WorkflowContext (no type parameters)
    For handlers that only perform side effects without sending messages or yielding outputs:

    .. code-block:: python

        class LoggingExecutor(Executor):
            @handler
            async def log_message(self, msg: str, ctx: WorkflowContext) -> None:
                print(f"Received: {msg}")  # Only logging, no outputs

    ### WorkflowContext[T_Out]
    Enables sending messages of type T_Out via `ctx.send_message()`:

    .. code-block:: python

        class ProcessorExecutor(Executor):
            @handler
            async def handler(self, msg: str, ctx: WorkflowContext[int]) -> None:
                await ctx.send_message(42)  # Can send int messages

    ### WorkflowContext[T_Out, T_W_Out]
    Enables both sending messages (T_Out) and yielding workflow outputs (T_W_Out):

    .. code-block:: python

        class DualOutputExecutor(Executor):
            @handler
            async def handler(self, msg: str, ctx: WorkflowContext[int, str]) -> None:
                await ctx.send_message(42)  # Send int message
                await ctx.yield_output("done")  # Yield str workflow output

    ## Function Executors
    Simple functions can be converted to executors using the `@executor` decorator:

    .. code-block:: python

        @executor
        async def process_text(text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(text.upper())


        # Or with custom ID:
        @executor(id="text_processor")
        def sync_process(text: str, ctx: WorkflowContext[str]) -> None:
            ctx.send_message(text.lower())  # Sync functions run in thread pool

    ## Sub-workflow Composition
    Executors can contain sub-workflows using WorkflowExecutor. Sub-workflows can make requests
    that parent workflows can intercept. See WorkflowExecutor documentation for details on
    workflow composition patterns and request/response handling.

    ## Implementation Notes
    - Do not call `execute()` directly - it's invoked by the workflow engine
    - Do not override `execute()` - define handlers using decorators instead
    - Each executor must have at least one `@handler` method
    - Handler method signatures are validated at initialization time
    """

    # Provide a default so static analyzers (e.g., pyright) don't require passing `id`.
    # Runtime still sets a concrete value in __init__.
    def __init__(
        self,
        id: str,
        *,
        type: str | None = None,
        type_: str | None = None,
        defer_discovery: bool = False,
        **_: Any,
    ) -> None:
        """Initialize the executor with a unique identifier.

        Args:
            id: A unique identifier for the executor.

        Keyword Args:
            type: The executor type name. If not provided, uses class name.
            type_: Alternative parameter name for executor type.
            defer_discovery: If True, defer handler method discovery until later.
            **_: Additional keyword arguments. Unused in this implementation.
        """
        if not id:
            raise ValueError("Executor ID must be a non-empty string.")

        resolved_type = type or type_ or self.__class__.__name__
        self.id = id
        self.type = resolved_type
        self.type_ = resolved_type

        from builtins import type as builtin_type

        self._handlers: dict[builtin_type[Any], Callable[[Any, WorkflowContext[Any, Any]], Awaitable[None]]] = {}
        self._handler_specs: list[dict[str, Any]] = []
        if not defer_discovery:
            self._discover_handlers()

            if not self._handlers:
                raise ValueError(
                    f"Executor {self.__class__.__name__} has no handlers defined. "
                    "Please define at least one handler using the @handler decorator."
                )

    async def execute(
        self,
        message: Any,
        source_executor_ids: list[str],
        shared_state: SharedState,
        runner_context: RunnerContext,
        trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ) -> None:
        """Execute the executor with a given message and context parameters.

        - Do not call this method directly - it is invoked by the workflow engine.
        - Do not override this method. Instead, define handlers using @handler decorator.

        Args:
            message: The message to be processed by the executor.
            source_executor_ids: The IDs of the source executors that sent messages to this executor.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
            trace_contexts: Optional trace contexts from multiple sources for OpenTelemetry propagation.
            source_span_ids: Optional source span IDs from multiple sources for linking.

        Returns:
            An awaitable that resolves to the result of the execution.
        """
        # Create processing span for tracing (gracefully handles disabled tracing)

        # Handle case where Message wrapper is passed instead of raw data
        if isinstance(message, Message):
            message = message.data

        with create_processing_span(
            self.id,
            self.__class__.__name__,
            type(message).__name__,
            source_trace_contexts=trace_contexts,
            source_span_ids=source_span_ids,
        ):
            # Find the handler and handler spec that matches the message type.
            handler: Callable[[Any, WorkflowContext[Any, Any]], Awaitable[None]] | None = None
            ctx_annotation = None
            for message_type in self._handlers:
                if is_instance_of(message, message_type):
                    handler = self._handlers[message_type]
                    # Find the corresponding handler spec for context annotation
                    for spec in self._handler_specs:
                        if spec.get("message_type") == message_type:
                            ctx_annotation = spec.get("ctx_annotation")
                            break
                    break

            if handler is None:
                raise RuntimeError(f"Executor {self.__class__.__name__} cannot handle message of type {type(message)}.")

            # Create the appropriate WorkflowContext based on handler specs
            context = self._create_context_for_handler(
                source_executor_ids=source_executor_ids,
                shared_state=shared_state,
                runner_context=runner_context,
                ctx_annotation=ctx_annotation,
                trace_contexts=trace_contexts,
                source_span_ids=source_span_ids,
            )

            # Invoke the handler with the message and context
            with _framework_event_origin():
                invoke_event = ExecutorInvokedEvent(self.id)
            await context.add_event(invoke_event)
            try:
                await handler(message, context)
            except Exception as exc:
                # Surface structured executor failure before propagating
                with _framework_event_origin():
                    failure_event = ExecutorFailedEvent(self.id, WorkflowErrorDetails.from_exception(exc))
                await context.add_event(failure_event)
                raise
            with _framework_event_origin():
                completed_event = ExecutorCompletedEvent(self.id)
            await context.add_event(completed_event)

    def _create_context_for_handler(
        self,
        source_executor_ids: list[str],
        shared_state: SharedState,
        runner_context: RunnerContext,
        ctx_annotation: Any,
        trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ) -> WorkflowContext[Any]:
        """Create the appropriate WorkflowContext based on the handler's context annotation.

        Args:
            source_executor_ids: The IDs of the source executors that sent messages to this executor.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
            ctx_annotation: The context annotation from the handler spec to determine which context type to create.
            trace_contexts: Optional trace contexts from multiple sources for OpenTelemetry propagation.
            source_span_ids: Optional source span IDs from multiple sources for linking.

        Returns:
            WorkflowContext[Any] based on the handler's context annotation.
        """
        # Create WorkflowContext
        return WorkflowContext(
            executor_id=self.id,
            source_executor_ids=source_executor_ids,
            shared_state=shared_state,
            runner_context=runner_context,
            trace_contexts=trace_contexts,
            source_span_ids=source_span_ids,
        )

    def _discover_handlers(self) -> None:
        """Discover message handlers in the executor class."""
        # Use __class__.__dict__ to avoid accessing pydantic's dynamic attributes
        for attr_name in dir(self.__class__):
            try:
                attr = getattr(self.__class__, attr_name)
                # Discover @handler methods
                if callable(attr) and hasattr(attr, "_handler_spec"):
                    handler_spec = attr._handler_spec  # type: ignore
                    message_type = handler_spec["message_type"]

                    # Keep full generic types for handler registration to avoid conflicts
                    # Different RequestResponse[T, U] specializations are distinct handler types

                    if self._handlers.get(message_type) is not None:
                        raise ValueError(f"Duplicate handler for type {message_type} in {self.__class__.__name__}")

                    # Get the bound method
                    bound_method = getattr(self, attr_name)
                    self._handlers[message_type] = bound_method

                    # Add to unified handler specs list
                    self._handler_specs.append({
                        "name": handler_spec["name"],
                        "message_type": message_type,
                        "output_types": handler_spec.get("output_types", []),
                        "workflow_output_types": handler_spec.get("workflow_output_types", []),
                        "ctx_annotation": handler_spec.get("ctx_annotation"),
                        "source": "class_method",  # Distinguish from instance handlers if needed
                    })
            except AttributeError:
                # Skip attributes that may not be accessible
                continue

    def can_handle(self, message: Any) -> bool:
        """Check if the executor can handle a given message type.

        Args:
            message: The message to check.

        Returns:
            True if the executor can handle the message type, False otherwise.
        """
        return any(is_instance_of(message, message_type) for message_type in self._handlers)

    def _register_instance_handler(
        self,
        name: str,
        func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]],
        message_type: type,
        ctx_annotation: Any,
        output_types: list[type],
        workflow_output_types: list[type],
    ) -> None:
        """Register a handler at instance level.

        Args:
            name: Name of the handler function for error reporting
            func: The async handler function to register
            message_type: Type of message this handler processes
            ctx_annotation: The WorkflowContext[T] annotation from the function
            output_types: List of output types for send_message()
            workflow_output_types: List of workflow output types for yield_output()
        """
        if message_type in self._handlers:
            raise ValueError(f"Handler for type {message_type} already registered in {self.__class__.__name__}")

        self._handlers[message_type] = func
        self._handler_specs.append({
            "name": name,
            "message_type": message_type,
            "ctx_annotation": ctx_annotation,
            "output_types": output_types,
            "workflow_output_types": workflow_output_types,
            "source": "instance_method",  # Distinguish from class handlers if needed
        })

    @property
    def input_types(self) -> list[type[Any]]:
        """Get the list of input types that this executor can handle.

        Returns:
            A list of the message types that this executor's handlers can process.
        """
        return list(self._handlers.keys())

    @property
    def output_types(self) -> list[type[Any]]:
        """Get the list of output types that this executor can produce via send_message().

        Returns:
            A list of the output types inferred from the handlers' WorkflowContext[T] annotations.
        """
        output_types: set[type[Any]] = set()

        # Collect output types from all handlers
        for handler_spec in self._handler_specs:
            handler_output_types = handler_spec.get("output_types", [])
            output_types.update(handler_output_types)

        return list(output_types)

    @property
    def workflow_output_types(self) -> list[type[Any]]:
        """Get the list of workflow output types that this executor can produce via yield_output().

        Returns:
            A list of the workflow output types inferred from handlers' WorkflowContext[T, U] annotations.
        """
        output_types: set[type[Any]] = set()

        # Collect workflow output types from all handlers
        for handler_spec in self._handler_specs:
            handler_workflow_output_types = handler_spec.get("workflow_output_types", [])
            output_types.update(handler_workflow_output_types)

        return list(output_types)

    def to_dict(self) -> dict[str, Any]:
        """Serialize executor definition for workflow topology export."""
        return {"id": self.id, "type": self.type}


# endregion: Executor

# region Handler Decorator


ExecutorT = TypeVar("ExecutorT", bound="Executor")
ContextT = TypeVar("ContextT", bound="WorkflowContext[Any, Any]")


def handler(
    func: Callable[[ExecutorT, Any, ContextT], Awaitable[Any]],
) -> (
    Callable[[ExecutorT, Any, ContextT], Awaitable[Any]]
    | Callable[
        [Callable[[ExecutorT, Any, ContextT], Awaitable[Any]]],
        Callable[[ExecutorT, Any, ContextT], Awaitable[Any]],
    ]
):
    """Decorator to register a handler for an executor.

    Args:
        func: The function to decorate. Can be None when used without parameters.

    Returns:
        The decorated function with handler metadata.

    Example:
        @handler
        async def handle_string(self, message: str, ctx: WorkflowContext[str]) -> None:
            ...

        @handler
        async def handle_data(self, message: dict, ctx: WorkflowContext[str | int]) -> None:
            ...
    """

    def decorator(
        func: Callable[[ExecutorT, Any, ContextT], Awaitable[Any]],
    ) -> Callable[[ExecutorT, Any, ContextT], Awaitable[Any]]:
        # Extract the message type and validate using unified validation
        message_type, ctx_annotation, inferred_output_types, inferred_workflow_output_types = (
            validate_function_signature(func, "Handler method")
        )

        # Get signature for preservation
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, message: Any, ctx: ContextT) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, message, ctx)

        # Preserve the original function signature for introspection during validation
        with contextlib.suppress(AttributeError, TypeError):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._handler_spec = {  # type: ignore
            "name": func.__name__,
            "message_type": message_type,
            # Keep output_types and workflow_output_types in spec for validators
            "output_types": inferred_output_types,
            "workflow_output_types": inferred_workflow_output_types,
            "ctx_annotation": ctx_annotation,
        }

        return wrapper

    return decorator(func)


# endregion: Handler Decorator
