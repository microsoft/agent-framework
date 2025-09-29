# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import importlib
import inspect
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from textwrap import shorten
from typing import Any, ClassVar, Generic, TypeVar, cast

from .._agents import AgentProtocol
from .._threads import AgentThread
from .._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage
from ..observability import create_processing_span
from ._checkpoint import WorkflowCheckpoint
from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,
    ExecutorCompletedEvent,
    ExecutorFailedEvent,
    ExecutorInvokedEvent,
    RequestInfoEvent,
    WorkflowErrorDetails,
    _framework_event_origin,  # type: ignore[reportPrivateUsage]
)
from ._model_utils import DictConvertible
from ._runner_context import Message, RunnerContext, _decode_checkpoint_value  # type: ignore
from ._shared_state import SharedState
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext, validate_function_signature

logger = logging.getLogger(__name__)
# region Executor


@dataclass
class PendingRequestDetails:
    """Lightweight information about a pending request captured in a checkpoint."""

    request_id: str
    prompt: str | None = None
    draft: str | None = None
    iteration: int | None = None
    source_executor_id: str | None = None
    original_request: "RequestInfoMessage | dict[str, Any] | None" = None


@dataclass
class WorkflowCheckpointSummary:
    """Human-readable summary of a workflow checkpoint."""

    checkpoint_id: str
    iteration_count: int
    targets: list[str]
    executor_states: list[str]
    status: str
    draft_preview: str | None
    pending_requests: list[PendingRequestDetails]


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
    ```python
    class MyExecutor(Executor):
        @handler
        async def handle_string(self, message: str, ctx: WorkflowContext) -> None:
            # This executor can handle 'str' input types
    ```
    Access via the `input_types` property.

    ### Output Types
    The types of messages an executor can send to other executors via `ctx.send_message()`:
    ```python
    class MyExecutor(Executor):
        @handler
        async def handle_data(self, message: str, ctx: WorkflowContext[int | bool]) -> None:
            # This executor can send 'int' or 'bool' messages
    ```
    Access via the `output_types` property.

    ### Workflow Output Types
    The types of data an executor can emit as workflow-level outputs via `ctx.yield_output()`:
    ```python
    class MyExecutor(Executor):
        @handler
        async def process(self, message: str, ctx: WorkflowContext[int, str]) -> None:
            # Can send 'int' messages AND yield 'str' workflow outputs
    ```
    Access via the `workflow_output_types` property.

    ## Handler Discovery
    Executors discover their capabilities through decorated methods:

    ### @handler Decorator
    Marks methods that process incoming messages:
    ```python
    class MyExecutor(Executor):
        @handler
        async def handle_text(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(message.upper())
    ```

    ### Sub-workflow Request Interception
    Use @handler methods to intercept sub-workflow requests:
    ```python
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
    ```

    ## Context Types
    Handler methods receive different WorkflowContext variants based on their type annotations:

    ### WorkflowContext (no type parameters)
    For handlers that only perform side effects without sending messages or yielding outputs:
    ```python
    class LoggingExecutor(Executor):
        @handler
        async def log_message(self, msg: str, ctx: WorkflowContext) -> None:
            print(f"Received: {msg}")  # Only logging, no outputs
    ```

    ### WorkflowContext[T_Out]
    Enables sending messages of type T_Out via `ctx.send_message()`:
    ```python
    class ProcessorExecutor(Executor):
        @handler
        async def handler(self, msg: str, ctx: WorkflowContext[int]) -> None:
            await ctx.send_message(42)  # Can send int messages
    ```

    ### WorkflowContext[T_Out, T_W_Out]
    Enables both sending messages (T_Out) and yielding workflow outputs (T_W_Out):
    ```python
    class DualOutputExecutor(Executor):
        @handler
        async def handler(self, msg: str, ctx: WorkflowContext[int, str]) -> None:
            await ctx.send_message(42)  # Send int message
            await ctx.yield_output("done")  # Yield str workflow output
    ```

    ## Function Executors
    Simple functions can be converted to executors using the `@executor` decorator:
    ```python
    @executor
    async def process_text(text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.upper())


    # Or with custom ID:
    @executor(id="text_processor")
    def sync_process(text: str, ctx: WorkflowContext[str]) -> None:
        ctx.send_message(text.lower())  # Sync functions run in thread pool
    ```

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


# region Request/Response Types
@dataclass
class RequestInfoMessage:
    """Base class for all request messages in workflows.

    Any message that should be routed to the RequestInfoExecutor for external
    handling must inherit from this class. This ensures type safety and makes
    the request/response pattern explicit.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for correlating requests and responses."""

    source_executor_id: str | None = None
    """ID of the executor expecting a response to this request.
    May differ from the executor that sent the request if intercepted and forwarded."""


TRequest = TypeVar("TRequest", bound="RequestInfoMessage")
TResponse = TypeVar("TResponse")


@dataclass
class RequestResponse(Generic[TRequest, TResponse]):
    """Response type for request/response correlation in workflows.

    This type is used by RequestInfoExecutor to create correlated responses
    that include the original request context for proper message routing.
    """

    data: TResponse
    """The response data returned from handling the request."""

    original_request: TRequest
    """The original request that this response corresponds to."""

    request_id: str
    """The ID of the original request."""


# endregion: Request/Response Types


# region Request Info Executor
class RequestInfoExecutor(Executor):
    """Built-in executor that handles request/response patterns in workflows.

    This executor acts as a gateway for external information requests. When it receives
    a request message, it saves the request details and emits a RequestInfoEvent. When
    a response is provided externally, it emits the response as a message.
    """

    _PENDING_SHARED_STATE_KEY: ClassVar[str] = "_af_pending_request_info"

    def __init__(self, id: str):
        """Initialize the RequestInfoExecutor with a unique ID.

        Args:
            id: Unique ID for this RequestInfoExecutor.
        """
        super().__init__(id=id)
        self._request_events: dict[str, RequestInfoEvent] = {}

    @handler
    async def run(self, message: RequestInfoMessage, ctx: WorkflowContext) -> None:
        """Run the RequestInfoExecutor with the given message."""
        # Use source_executor_id from message if available, otherwise fall back to context
        source_executor_id = message.source_executor_id or ctx.get_source_executor_id()

        event = RequestInfoEvent(
            request_id=message.request_id,
            source_executor_id=source_executor_id,
            request_type=type(message),
            request_data=message,
        )
        self._request_events[message.request_id] = event
        await self._record_pending_request_snapshot(message, source_executor_id, ctx)
        await ctx.add_event(event)

    async def handle_response(
        self,
        response_data: Any,
        request_id: str,
        ctx: WorkflowContext[RequestResponse[RequestInfoMessage, Any]],
    ) -> None:
        """Handle a response to a request.

        Args:
            request_id: The ID of the request to which this response corresponds.
            response_data: The data returned in the response.
            ctx: The workflow context for sending the response.
        """
        event = self._request_events.get(request_id)
        if event is None:
            event = await self._rehydrate_request_event(request_id, ctx)
        if event is None:
            raise ValueError(f"No request found with ID: {request_id}")

        self._request_events.pop(request_id, None)

        # Create a correlated response that includes both the response data and original request
        if not isinstance(event.data, RequestInfoMessage):
            raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
        correlated_response = RequestResponse(data=response_data, original_request=event.data, request_id=request_id)
        await ctx.send_message(correlated_response, target_id=event.source_executor_id)

        await self._clear_pending_request_snapshot(request_id, ctx)

    async def _record_pending_request_snapshot(
        self,
        request: RequestInfoMessage,
        source_executor_id: str,
        ctx: WorkflowContext[Any],
    ) -> None:
        snapshot = self._build_request_snapshot(request, source_executor_id)

        pending = await self._load_pending_request_state(ctx)
        pending[request.request_id] = snapshot
        await self._persist_pending_request_state(pending, ctx)
        await self._write_executor_state(ctx, pending)

    async def _clear_pending_request_snapshot(self, request_id: str, ctx: WorkflowContext[Any]) -> None:
        pending = await self._load_pending_request_state(ctx)
        if request_id in pending:
            pending.pop(request_id, None)
            await self._persist_pending_request_state(pending, ctx)
        await self._write_executor_state(ctx, pending)

    async def _load_pending_request_state(self, ctx: WorkflowContext[Any]) -> dict[str, Any]:
        try:
            existing = await ctx.get_shared_state(self._PENDING_SHARED_STATE_KEY)
        except KeyError:
            return {}
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read pending request state: {exc}")
            return {}

        if not isinstance(existing, dict):
            if existing not in (None, {}):
                logger.warning(
                    f"RequestInfoExecutor {self.id} encountered non-dict pending state "
                    f"({type(existing).__name__}); resetting."
                )
            return {}

        return dict(existing)  # type: ignore[arg-type]

    async def _persist_pending_request_state(self, pending: dict[str, Any], ctx: WorkflowContext[Any]) -> None:
        await self._safe_set_shared_state(ctx, pending)
        await self._safe_set_runner_state(ctx, pending)

    async def _safe_set_shared_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        try:
            await ctx.set_shared_state(self._PENDING_SHARED_STATE_KEY, pending)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to update shared pending state: {exc}")

    async def _safe_set_runner_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        try:
            await ctx.set_state({"pending_requests": pending})
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to update runner state with pending requests: {exc}")

    def snapshot_state(self) -> dict[str, Any]:
        """Serialize pending requests so checkpoint restoration can resume seamlessly."""

        def _encode_event(event: RequestInfoEvent) -> dict[str, Any]:
            request_data = event.data
            payload: dict[str, Any]
            data_cls = request_data.__class__ if request_data is not None else type(None)

            payload = self._encode_request_payload(request_data, data_cls)

            return {
                "source_executor_id": event.source_executor_id,
                "request_type": f"{event.request_type.__module__}:{event.request_type.__qualname__}",
                "request_data": payload,
            }

        return {
            "request_events": {rid: _encode_event(event) for rid, event in self._request_events.items()},
        }

    def _encode_request_payload(self, request_data: RequestInfoMessage | None, data_cls: type[Any]) -> dict[str, Any]:
        if request_data is None or isinstance(request_data, (str, int, float, bool)):
            return {
                "kind": "raw",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": request_data,
            }

        if is_dataclass(request_data) and not isinstance(request_data, type):
            dataclass_instance = cast(Any, request_data)
            safe_value = self._make_json_safe(asdict(dataclass_instance))
            return {
                "kind": "dataclass",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        to_dict_fn = getattr(request_data, "to_dict", None)
        if callable(to_dict_fn):
            try:
                dumped = to_dict_fn()
            except TypeError:
                dumped = to_dict_fn()
            safe_value = self._make_json_safe(dumped)
            return {
                "kind": "dict",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        to_json_fn = getattr(request_data, "to_json", None)
        if callable(to_json_fn):
            try:
                dumped = to_json_fn()
            except TypeError:
                dumped = to_json_fn()
            converted = dumped
            if isinstance(dumped, (str, bytes, bytearray)):
                decoded: str | bytes | bytearray
                if isinstance(dumped, (bytes, bytearray)):
                    try:
                        decoded = dumped.decode()
                    except Exception:
                        decoded = dumped
                else:
                    decoded = dumped
                try:
                    converted = json.loads(decoded)
                except Exception:
                    converted = decoded
            safe_value = self._make_json_safe(converted)
            return {
                "kind": "dict" if isinstance(converted, dict) else "json",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        details = self._serialise_request_details(request_data)
        if details is not None:
            safe_value = self._make_json_safe(details)
            return {
                "kind": "raw",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        safe_value = self._make_json_safe(request_data)
        return {
            "kind": "raw",
            "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
            "value": safe_value,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore pending request bookkeeping from checkpoint state."""
        self._request_events.clear()
        stored_events = state.get("request_events", {})

        for request_id, payload in stored_events.items():
            request_type_qual = payload.get("request_type", "")
            try:
                request_type = self._import_qualname(request_type_qual)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug(
                    "RequestInfoExecutor %s failed to import %s during restore: %s",
                    self.id,
                    request_type_qual,
                    exc,
                )
                request_type = RequestInfoMessage
            request_data_meta = payload.get("request_data", {})
            request_data = self._decode_request_data(request_data_meta)
            event = RequestInfoEvent(
                request_id=request_id,
                source_executor_id=payload.get("source_executor_id", ""),
                request_type=request_type,
                request_data=request_data,
            )
            self._request_events[request_id] = event

    @staticmethod
    def _import_qualname(qualname: str) -> type[Any]:
        module_name, _, type_name = qualname.partition(":")
        if not module_name or not type_name:
            raise ValueError(f"Invalid qualified name: {qualname}")
        module = importlib.import_module(module_name)
        attr: Any = module
        for part in type_name.split("."):
            attr = getattr(attr, part)
        if not isinstance(attr, type):
            raise TypeError(f"Resolved object is not a type: {qualname}")
        return attr

    def _decode_request_data(self, metadata: dict[str, Any]) -> RequestInfoMessage:
        kind = metadata.get("kind")
        type_name = metadata.get("type", "")
        value: Any = metadata.get("value", {})
        if type_name:
            try:
                imported = self._import_qualname(type_name)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug(
                    "RequestInfoExecutor %s failed to import %s during decode: %s",
                    self.id,
                    type_name,
                    exc,
                )
                imported = RequestInfoMessage
        else:
            imported = RequestInfoMessage
        target_cls: type[RequestInfoMessage]
        if isinstance(imported, type) and issubclass(imported, RequestInfoMessage):
            target_cls = imported
        else:
            target_cls = RequestInfoMessage

        if kind == "dataclass" and isinstance(value, dict):
            with contextlib.suppress(TypeError):
                return target_cls(**value)  # type: ignore[arg-type]

        # Backwards-compat handling for checkpoints that used to store pydantic as "dict"
        if kind in {"dict", "pydantic", "json"} and isinstance(value, dict):
            from_dict = getattr(target_cls, "from_dict", None)
            if callable(from_dict):
                with contextlib.suppress(Exception):
                    return cast(RequestInfoMessage, from_dict(value))

        if kind == "json" and isinstance(value, str):
            from_json = getattr(target_cls, "from_json", None)
            if callable(from_json):
                with contextlib.suppress(Exception):
                    return cast(RequestInfoMessage, from_json(value))
            with contextlib.suppress(Exception):
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return self._decode_request_data({"kind": "dict", "type": type_name, "value": parsed})

        if isinstance(value, dict):
            with contextlib.suppress(TypeError):
                return target_cls(**value)  # type: ignore[arg-type]
            instance = object.__new__(target_cls)
            instance.__dict__.update(value)  # type: ignore[arg-type]
            return instance

        with contextlib.suppress(Exception):
            return target_cls()
        return RequestInfoMessage()

    async def _write_executor_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        state = self.snapshot_state()
        state["pending_requests"] = pending
        try:
            await ctx.set_state(state)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to persist executor state: {exc}")

    def _build_request_snapshot(
        self,
        request: RequestInfoMessage,
        source_executor_id: str,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "request_id": request.request_id,
            "source_executor_id": source_executor_id,
            "request_type": f"{type(request).__module__}:{type(request).__name__}",
            "summary": repr(request),
        }

        details = self._serialise_request_details(request)
        if details:
            snapshot["details"] = details
            for key in ("prompt", "draft", "iteration"):
                if key in details and key not in snapshot:
                    snapshot[key] = details[key]

        return snapshot

    def _serialise_request_details(self, request: RequestInfoMessage) -> dict[str, Any] | None:
        if is_dataclass(request):
            data = self._make_json_safe(asdict(request))
            if isinstance(data, dict):
                return cast(dict[str, Any], data)
            return None

        to_dict = getattr(request, "to_dict", None)
        if callable(to_dict):
            try:
                dump = self._make_json_safe(to_dict())
            except TypeError:
                dump = self._make_json_safe(to_dict())
            if isinstance(dump, dict):
                return cast(dict[str, Any], dump)
            return None

        to_json = getattr(request, "to_json", None)
        if callable(to_json):
            try:
                raw = to_json()
            except TypeError:
                raw = to_json()
            converted = raw
            if isinstance(raw, (str, bytes, bytearray)):
                decoded: str | bytes | bytearray
                if isinstance(raw, (bytes, bytearray)):
                    try:
                        decoded = raw.decode()
                    except Exception:
                        decoded = raw
                else:
                    decoded = raw
                try:
                    converted = json.loads(decoded)
                except Exception:
                    converted = decoded
            dump = self._make_json_safe(converted)
            if isinstance(dump, dict):
                return cast(dict[str, Any], dump)
            return None

        attrs = getattr(request, "__dict__", None)
        if isinstance(attrs, dict):
            cleaned = self._make_json_safe(attrs)
            if isinstance(cleaned, dict):
                return cast(dict[str, Any], cleaned)

        return None

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            safe_dict: dict[str, Any] = {}
            for key, val in value.items():  # type: ignore[attr-defined]
                safe_dict[str(key)] = self._make_json_safe(val)  # type: ignore[arg-type]
            return safe_dict
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._make_json_safe(item) for item in value]  # type: ignore[misc]
        return repr(value)

    async def has_pending_request(self, request_id: str, ctx: WorkflowContext[Any]) -> bool:
        if request_id in self._request_events:
            return True
        snapshot = await self._get_pending_request_snapshot(request_id, ctx)
        return snapshot is not None

    async def _rehydrate_request_event(
        self,
        request_id: str,
        ctx: WorkflowContext[Any],
    ) -> RequestInfoEvent | None:
        snapshot = await self._get_pending_request_snapshot(request_id, ctx)
        if snapshot is None:
            return None

        source_executor_id = snapshot.get("source_executor_id")
        if not isinstance(source_executor_id, str) or not source_executor_id:
            return None

        request = self._construct_request_from_snapshot(snapshot)
        if request is None:
            return None

        event = RequestInfoEvent(
            request_id=request_id,
            source_executor_id=source_executor_id,
            request_type=type(request),
            request_data=request,
        )
        self._request_events[request_id] = event
        return event

    async def _get_pending_request_snapshot(self, request_id: str, ctx: WorkflowContext[Any]) -> dict[str, Any] | None:
        pending = await self._collect_pending_request_snapshots(ctx)
        snapshot = pending.get(request_id)
        if snapshot is None:
            return None
        return snapshot

    async def _collect_pending_request_snapshots(self, ctx: WorkflowContext[Any]) -> dict[str, dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}

        try:
            shared_pending = await ctx.get_shared_state(self._PENDING_SHARED_STATE_KEY)
        except KeyError:
            shared_pending = None
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read shared pending state during rehydrate: {exc}")
            shared_pending = None

        if isinstance(shared_pending, dict):
            for key, value in shared_pending.items():  # type: ignore[attr-defined]
                if isinstance(key, str) and isinstance(value, dict):
                    combined[key] = cast(dict[str, Any], value)

        try:
            state = await ctx.get_state()
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read runner state during rehydrate: {exc}")
            state = None

        if isinstance(state, dict):
            state_pending = state.get("pending_requests")
            if isinstance(state_pending, dict):
                for key, value in state_pending.items():  # type: ignore[attr-defined]
                    if isinstance(key, str) and isinstance(value, dict) and key not in combined:
                        combined[key] = cast(dict[str, Any], value)

        return combined

    def _construct_request_from_snapshot(self, snapshot: dict[str, Any]) -> RequestInfoMessage | None:
        details_raw = snapshot.get("details")
        details: dict[str, Any] = cast(dict[str, Any], details_raw) if isinstance(details_raw, dict) else {}

        request_cls: type[RequestInfoMessage] = RequestInfoMessage
        request_type_str = snapshot.get("request_type")
        if isinstance(request_type_str, str) and ":" in request_type_str:
            module_name, class_name = request_type_str.split(":", 1)
            try:
                module = importlib.import_module(module_name)
                candidate = getattr(module, class_name)
                if isinstance(candidate, type) and issubclass(candidate, RequestInfoMessage):
                    request_cls = candidate
            except Exception as exc:
                logger.warning(f"RequestInfoExecutor {self.id} could not import {module_name}.{class_name}: {exc}")
                request_cls = RequestInfoMessage

        request: RequestInfoMessage | None = self._instantiate_request(request_cls, details)

        if request is None and request_cls is not RequestInfoMessage:
            request = self._instantiate_request(RequestInfoMessage, details)

        if request is None:
            logger.warning(
                f"RequestInfoExecutor {self.id} could not reconstruct request "
                f"{request_type_str or RequestInfoMessage.__name__} from snapshot keys {sorted(details.keys())}"
            )
            return None

        for key, value in details.items():
            if key == "request_id":
                continue
            try:
                setattr(request, key, value)
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not set attribute {key} on {type(request).__name__}: {exc}"
                )
                continue

        snapshot_request_id = snapshot.get("request_id")
        if isinstance(snapshot_request_id, str) and snapshot_request_id:
            try:
                request.request_id = snapshot_request_id
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not apply snapshot "
                    f"request_id to {type(request).__name__}: {exc}"
                )

        return request

    def _instantiate_request(
        self,
        request_cls: type[RequestInfoMessage],
        details: dict[str, Any],
    ) -> RequestInfoMessage | None:
        try:
            from_dict = getattr(request_cls, "from_dict", None)
            if callable(from_dict):
                return cast(RequestInfoMessage, from_dict(details))
        except (TypeError, ValueError) as exc:
            logger.debug(f"RequestInfoExecutor {self.id} failed to hydrate {request_cls.__name__} via from_dict: {exc}")
        except Exception as exc:
            logger.warning(
                f"RequestInfoExecutor {self.id} encountered unexpected error during "
                f"{request_cls.__name__}.from_dict: {exc}"
            )

        if is_dataclass(request_cls):
            try:
                field_names = {f.name for f in fields(request_cls)}
                ctor_kwargs = {name: details[name] for name in field_names if name in details}
                return request_cls(**ctor_kwargs)
            except (TypeError, ValueError) as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not instantiate dataclass "
                    f"{request_cls.__name__} with snapshot data: {exc}"
                )
            except Exception as exc:
                logger.warning(
                    f"RequestInfoExecutor {self.id} encountered unexpected error "
                    f"constructing dataclass {request_cls.__name__}: {exc}"
                )

        try:
            instance = request_cls()
        except Exception as exc:
            logger.warning(
                f"RequestInfoExecutor {self.id} could not instantiate {request_cls.__name__} without arguments: {exc}"
            )
            return None

        for key, value in details.items():
            if key == "request_id":
                continue
            try:
                setattr(instance, key, value)
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not set attribute {key} on "
                    f"{request_cls.__name__} during instantiation: {exc}"
                )
                continue

        return instance

    @staticmethod
    def pending_requests_from_checkpoint(
        checkpoint: WorkflowCheckpoint,
        *,
        request_executor_ids: Iterable[str] | None = None,
    ) -> list[PendingRequestDetails]:
        executor_filter: set[str] | None = None
        if request_executor_ids is not None:
            executor_filter = {str(value) for value in request_executor_ids}

        pending: dict[str, PendingRequestDetails] = {}

        shared_map = checkpoint.shared_state.get(RequestInfoExecutor._PENDING_SHARED_STATE_KEY)
        if isinstance(shared_map, Mapping):
            for request_id, snapshot in shared_map.items():  # type: ignore[attr-defined]
                RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)  # type: ignore[arg-type]

        for state in checkpoint.executor_states.values():
            if not isinstance(state, Mapping):
                continue
            inner = state.get("pending_requests")
            if isinstance(inner, Mapping):
                for request_id, snapshot in inner.items():  # type: ignore[attr-defined]
                    RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)  # type: ignore[arg-type]

        for source_id, message_list in checkpoint.messages.items():
            if executor_filter is not None and source_id not in executor_filter:
                continue
            if not isinstance(message_list, list):
                continue
            for message in message_list:
                if not isinstance(message, Mapping):
                    continue
                payload = _decode_checkpoint_value(message.get("data"))
                RequestInfoExecutor._merge_message_payload(pending, payload, message)

        return list(pending.values())

    @staticmethod
    def checkpoint_summary(
        checkpoint: WorkflowCheckpoint,
        *,
        request_executor_ids: Iterable[str] | None = None,
        preview_width: int = 70,
    ) -> WorkflowCheckpointSummary:
        targets = sorted(checkpoint.messages.keys())
        executor_states = sorted(checkpoint.executor_states.keys())
        pending = RequestInfoExecutor.pending_requests_from_checkpoint(
            checkpoint, request_executor_ids=request_executor_ids
        )

        draft_preview: str | None = None
        for entry in pending:
            if entry.draft:
                draft_preview = shorten(entry.draft, width=preview_width, placeholder="…")
                break

        status = "idle"
        if pending:
            status = "awaiting human response"
        elif not checkpoint.messages and "finalise" in executor_states:
            status = "completed"
        elif checkpoint.messages:
            status = "awaiting next superstep"
        elif request_executor_ids is not None and any(tid in targets for tid in request_executor_ids):
            status = "awaiting request delivery"

        return WorkflowCheckpointSummary(
            checkpoint_id=checkpoint.checkpoint_id,
            iteration_count=checkpoint.iteration_count,
            targets=targets,
            executor_states=executor_states,
            status=status,
            draft_preview=draft_preview,
            pending_requests=pending,
        )

    @staticmethod
    def _merge_snapshot(
        pending: dict[str, PendingRequestDetails],
        request_id: str,
        snapshot: Any,
    ) -> None:
        if not request_id or not isinstance(snapshot, Mapping):
            return

        details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))

        RequestInfoExecutor._apply_update(
            details,
            prompt=snapshot.get("prompt"),  # type: ignore[attr-defined]
            draft=snapshot.get("draft"),  # type: ignore[attr-defined]
            iteration=snapshot.get("iteration"),  # type: ignore[attr-defined]
            source_executor_id=snapshot.get("source_executor_id"),  # type: ignore[attr-defined]
        )

        extra = snapshot.get("details")  # type: ignore[attr-defined]
        if isinstance(extra, Mapping):
            RequestInfoExecutor._apply_update(
                details,
                prompt=extra.get("prompt"),  # type: ignore[attr-defined]
                draft=extra.get("draft"),  # type: ignore[attr-defined]
                iteration=extra.get("iteration"),  # type: ignore[attr-defined]
            )

    @staticmethod
    def _merge_message_payload(
        pending: dict[str, PendingRequestDetails],
        payload: Any,
        raw_message: Mapping[str, Any],
    ) -> None:
        if isinstance(payload, RequestResponse):
            request_id = payload.request_id or RequestInfoExecutor._get_field(payload.original_request, "request_id")  # type: ignore[arg-type]
            if not request_id:
                return
            details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
            RequestInfoExecutor._apply_update(
                details,
                prompt=RequestInfoExecutor._get_field(payload.original_request, "prompt"),  # type: ignore[arg-type]
                draft=RequestInfoExecutor._get_field(payload.original_request, "draft"),  # type: ignore[arg-type]
                iteration=RequestInfoExecutor._get_field(payload.original_request, "iteration"),  # type: ignore[arg-type]
                source_executor_id=raw_message.get("source_id"),
                original_request=payload.original_request,  # type: ignore[arg-type]
            )
        elif isinstance(payload, RequestInfoMessage):
            request_id = getattr(payload, "request_id", None)
            if not request_id:
                return
            details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
            RequestInfoExecutor._apply_update(
                details,
                prompt=getattr(payload, "prompt", None),
                draft=getattr(payload, "draft", None),
                iteration=getattr(payload, "iteration", None),
                source_executor_id=raw_message.get("source_id"),
                original_request=payload,
            )

    @staticmethod
    def _apply_update(
        details: PendingRequestDetails,
        *,
        prompt: Any = None,
        draft: Any = None,
        iteration: Any = None,
        source_executor_id: Any = None,
        original_request: Any = None,
    ) -> None:
        if prompt and not details.prompt:
            details.prompt = str(prompt)
        if draft and not details.draft:
            details.draft = str(draft)
        if iteration is not None and details.iteration is None:
            coerced = RequestInfoExecutor._coerce_int(iteration)
            if coerced is not None:
                details.iteration = coerced
        if source_executor_id and not details.source_executor_id:
            details.source_executor_id = str(source_executor_id)
        if original_request is not None and details.original_request is None:
            details.original_request = original_request

    @staticmethod
    def _get_field(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, Mapping):
            return obj.get(key)  # type: ignore[attr-defined,return-value]
        return getattr(obj, key, None)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


# endregion: Request Info Executor

# region Agent Executor


@dataclass
class AgentExecutorRequest:
    """A request to an agent executor.

    Attributes:
        messages: A list of chat messages to be processed by the agent.
        should_respond: A flag indicating whether the agent should respond to the messages.
            If False, the messages will be saved to the executor's cache but not sent to the agent.
    """

    messages: list[ChatMessage]
    should_respond: bool = True


@dataclass
class AgentExecutorResponse:
    """A response from an agent executor.

    Attributes:
        executor_id: The ID of the executor that generated the response.
    agent_run_response: The underlying agent run response (unaltered from client).
    full_conversation: The full conversation context (prior inputs + all assistant/tool outputs) that
        should be used when chaining to another AgentExecutor. This prevents downstream agents losing
        user prompts while keeping the emitted AgentRunEvent text faithful to the raw agent output.
    """

    executor_id: str
    agent_run_response: AgentRunResponse
    full_conversation: list[ChatMessage] | None = None


class AgentExecutor(Executor):
    """built-in executor that wraps an agent for handling messages."""

    def __init__(
        self,
        agent: AgentProtocol,
        *,
        agent_thread: AgentThread | None = None,
        streaming: bool = False,
        id: str | None = None,
    ):
        """Initialize the executor with a unique identifier.

        Args:
            agent: The agent to be wrapped by this executor.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            streaming: Enable streaming (emits incremental AgentRunUpdateEvent events) vs single response.
            id: A unique identifier for the executor. If None, a new UUID will be generated.
        """
        # Prefer provided id; else use agent.name if present; else generate deterministic prefix
        if id is not None:
            exec_id = id
        else:
            agent_name = agent.name
            if agent_name:
                exec_id = str(agent_name)
            else:
                logger.warning("Agent has no name, using fallback ID 'executor_unnamed'")
                exec_id = "executor_unnamed"
        super().__init__(exec_id)
        self._agent = agent
        self._agent_thread = agent_thread or self._agent.get_new_thread()
        self._streaming = streaming
        self._cache: list[ChatMessage] = []

    async def _run_agent_and_emit(self, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Execute the underlying agent, emit events, and enqueue response.

        Terminal detection is handled centrally in Runner.
        This method only produces AgentRunEvent/AgentRunUpdateEvent plus enqueues an
        AgentExecutorResponse message for routing.
        """
        if self._streaming:
            updates: list[AgentRunResponseUpdate] = []
            async for update in self._agent.run_stream(
                self._cache,
                thread=self._agent_thread,
            ):
                # Skip empty updates (no textual or structural content)
                if not update:
                    continue
                contents = getattr(update, "contents", None)
                text_val = getattr(update, "text", "")
                has_text_content = False
                if contents:
                    for c in contents:
                        if getattr(c, "text", None):
                            has_text_content = True
                            break
                if not (text_val or has_text_content):
                    continue
                updates.append(update)
                await ctx.add_event(AgentRunUpdateEvent(self.id, update))
            response = AgentRunResponse.from_agent_run_response_updates(updates)
        else:
            response = await self._agent.run(
                self._cache,
                thread=self._agent_thread,
            )
            await ctx.add_event(AgentRunEvent(self.id, response))

        # Always construct a full conversation snapshot from inputs (cache)
        # plus agent outputs (agent_run_response.messages). Do not mutate
        # response.messages so AgentRunEvent remains faithful to the raw output.
        full_conversation: list[ChatMessage] = list(self._cache) + list(response.messages)

        agent_response = AgentExecutorResponse(self.id, response, full_conversation=full_conversation)
        await ctx.send_message(agent_response)
        self._cache.clear()

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Handle an AgentExecutorRequest (canonical input).

        This is the standard path: extend cache with provided messages; if should_respond
        run the agent and emit an AgentExecutorResponse downstream.
        """
        self._cache.extend(request.messages)
        if request.should_respond:
            await self._run_agent_and_emit(ctx)

    @handler
    async def from_response(self, prior: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Enable seamless chaining: accept a prior AgentExecutorResponse as input.

        Strategy: treat the prior response's messages as the conversation state and
        immediately run the agent to produce a new response.
        """
        # Replace cache with full conversation if available, else fall back to agent_run_response messages.
        if prior.full_conversation is not None:
            self._cache = list(prior.full_conversation)
        else:
            self._cache = list(prior.agent_run_response.messages)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_str(self, text: str, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Accept a raw user prompt string and run the agent (one-shot)."""
        self._cache = [ChatMessage(role="user", text=text)]  # type: ignore[arg-type]
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorResponse]) -> None:  # type: ignore[name-defined]
        """Accept a single ChatMessage as input."""
        self._cache = [message]
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_messages(self, messages: list[ChatMessage], ctx: WorkflowContext[AgentExecutorResponse]) -> None:  # type: ignore[name-defined]
        """Accept a list of ChatMessage objects as conversation context."""
        self._cache = list(messages)
        await self._run_agent_and_emit(ctx)


# endregion: Agent Executor
