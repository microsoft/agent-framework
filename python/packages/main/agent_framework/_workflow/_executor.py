# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import importlib
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from textwrap import shorten
from typing import Any, ClassVar, Generic, TypeVar, cast, overload

from pydantic import Field

from .._agents import AgentProtocol
from .._pydantic import AFBaseModel
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
from ._runner_context import Message, RunnerContext, _decode_checkpoint_value
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


class Executor(AFBaseModel):
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

    ### Request Types
    The types of sub-workflow requests an executor can intercept via `@intercepts_request`:
    ```python
    class ParentExecutor(Executor):
        @intercepts_request
        async def handle_request(
            self,
            request: MyRequest,
            ctx: WorkflowContext,
        ) -> RequestResponse[MyRequest, str]:
            # Can intercept 'MyRequest' from sub-workflows
    ```
    Access via the `request_types` property.

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

    ### @intercepts_request Decorator
    Marks methods that intercept sub-workflow requests:
    ```python
    class ParentExecutor(Executor):
        @intercepts_request
        async def check_domain(
            self, request: DomainRequest, ctx: WorkflowContext
        ) -> RequestResponse[DomainRequest, bool]:
            if self.is_allowed(request.domain):
                return RequestResponse.handled(True)
            return RequestResponse.forward()
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
    - Each executor must have at least one `@handler` or `@intercepts_request` method
    - Handler method signatures are validated at initialization time
    """

    # Provide a default so static analyzers (e.g., pyright) don't require passing `id`.
    # Runtime still sets a concrete value in __init__.
    id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the executor",
    )
    type_: str = Field(default="", alias="type", description="The type of executor, corresponding to the class name")

    def __init__(self, id: str, **kwargs: Any) -> None:
        """Initialize the executor with a unique identifier.

        Args:
            id: A unique identifier for the executor.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        if not id:
            raise ValueError("Executor ID must be a non-empty string.")

        kwargs.update({"id": id})
        if "type" not in kwargs and "type_" not in kwargs:
            kwargs["type_"] = self.__class__.__name__

        super().__init__(**kwargs)

        self._handlers: dict[type, Callable[[Any, WorkflowContext[Any, Any]], Awaitable[None]]] = {}
        self._request_interceptors: dict[type | str, list[dict[str, Any]]] = {}
        self._handler_specs: list[dict[str, Any]] = []
        self._discover_handlers()

        if not self._handlers and not self._request_interceptors:
            raise ValueError(
                f"Executor {self.__class__.__name__} has no handlers defined. "
                "Please define at least one handler using the @handler decorator "
                "or @intercepts_request decorator."
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
            # This includes the self._handle_sub_workflow_request handler for SubWorkflowRequestInfo.
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
        """Discover message handlers and request interceptors in the executor class."""
        # Use __class__.__dict__ to avoid accessing pydantic's dynamic attributes
        for attr_name in dir(self.__class__):
            try:
                attr = getattr(self.__class__, attr_name)
                if callable(attr):
                    # Discover @handler methods
                    if hasattr(attr, "_handler_spec"):
                        handler_spec = attr._handler_spec  # type: ignore
                        message_type = handler_spec["message_type"]

                        # Keep full generic types for handler registration to avoid conflicts
                        # Different RequestResponse[T, U] specializations are distinct handler types

                        if self._handlers.get(message_type) is not None:
                            raise ValueError(f"Duplicate handler for type {message_type} in {self.__class__.__name__}")

                        # RequestInfoExecutor is allowed to handle SubWorkflowRequestInfo directly
                        # but other executors should use @intercepts_request
                        if message_type is SubWorkflowRequestInfo and not isinstance(self, RequestInfoExecutor):
                            raise ValueError(
                                f"Executor {self.__class__.__name__} cannot define a handler for "
                                "SubWorkflowRequestInfo directly. "
                                f"Use @intercepts_request decorator to intercept sub-workflow requests."
                            )

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

                    # Discover @intercepts_request methods
                    if hasattr(attr, "_intercepts_request"):
                        # Get the bound method for interceptors
                        bound_method = getattr(self, attr_name)
                        interceptor_info = {
                            "method": bound_method,
                            "from_workflow": getattr(attr, "_from_workflow", None),
                            "condition": getattr(attr, "_intercept_condition", None),
                        }
                        request_type = attr._intercepts_request  # type: ignore
                        if request_type not in self._request_interceptors:
                            self._request_interceptors[request_type] = []
                        self._request_interceptors[request_type].append(interceptor_info)

                        # We need to register the handler for SubWorkflowRequestInfo
                        # if not already registered.
                        if SubWorkflowRequestInfo not in self._handlers:
                            self._handlers[SubWorkflowRequestInfo] = self._handle_sub_workflow_request
                            self._handler_specs.append({
                                "name": attr_name,
                                "message_type": SubWorkflowRequestInfo,
                                "output_types": [SubWorkflowResponse, SubWorkflowRequestInfo, RequestInfoMessage],
                                "workflow_output_types": [],
                                "ctx_annotation": WorkflowContext[
                                    SubWorkflowRequestInfo | SubWorkflowResponse | RequestInfoMessage
                                ],
                                "source": "class_method",
                            })
            except AttributeError:
                # Skip attributes that may not be accessible
                continue

    async def _handle_sub_workflow_request(
        self,
        request: "SubWorkflowRequestInfo",
        ctx: WorkflowContext["SubWorkflowResponse | SubWorkflowRequestInfo | RequestInfoMessage"],
    ) -> None:
        """Automatic routing to @intercepts_request methods.

        This is only active for executors that have @intercepts_request methods.
        """
        # Try to find a matching interceptor for the request and execute it
        for request_type, interceptor_list in self._request_interceptors.items():
            if self._does_request_match_type(request.data, request_type):
                for interceptor_info in interceptor_list:
                    if self._does_interceptor_apply_to_request(request, interceptor_info):
                        logger.debug(
                            f"Executor {self.id} intercepting request {request.request_id} "
                            f"of type {type(request.data).__name__} from sub-workflow {request.sub_workflow_id}"
                        )
                        await self._execute_interceptor(request, interceptor_info, ctx)
                        return  # Only the first matching interceptor is executed
        logger.debug(
            f"Executor {self.id} has no matching interceptor for request {request.request_id} "
            f"of type {type(request.data).__name__} from sub-workflow {request.sub_workflow_id}; forwarding "
            "inner request to RequestInfoExecutor for external handling."
        )
        # No interceptor found - forward inner request to RequestInfoExecutor
        await ctx.send_message(request.data)

    def _does_request_match_type(self, request_data: Any, request_type: type | str) -> bool:
        """Check if request data matches the expected type.

        Args:
            request_data: The request data to check
            request_type: The type to match against (can be a type or string)

        Returns:
            True if the request matches the type, False otherwise.
        """
        if isinstance(request_type, type):
            return is_instance_of(request_data, request_type)

        return (
            isinstance(request_type, str)
            and hasattr(request_data, "__class__")
            and request_data.__class__.__name__ == request_type
        )

    def _does_interceptor_apply_to_request(
        self, request: "SubWorkflowRequestInfo", interceptor_info: dict[str, Any]
    ) -> bool:
        """Check if an interceptor applies to the given request.

        Args:
            request: The sub-workflow request
            interceptor_info: Information about the interceptor

        Returns:
            True if the interceptor should handle this request, False otherwise.
        """
        # Check workflow scope if specified
        from_workflow = interceptor_info["from_workflow"]
        if from_workflow and request.sub_workflow_id != from_workflow:
            return False

        # Check additional condition
        condition = interceptor_info["condition"]
        return not (condition and not condition(request))

    async def _execute_interceptor(
        self,
        request: "SubWorkflowRequestInfo",
        interceptor_info: dict[str, Any],
        ctx: WorkflowContext["SubWorkflowResponse | SubWorkflowRequestInfo | RequestInfoMessage"],
    ) -> None:
        """Execute a single interceptor method.

        Args:
            request: The sub-workflow request
            interceptor_info: Information about the interceptor method
            ctx: The workflow context
        """
        method = interceptor_info["method"]
        response = await method(request.data, ctx)

        if not isinstance(response, RequestResponse):
            raise RuntimeError(
                f"Interceptor method {method.__name__} must return RequestResponse, got {type(response)}"
            )

        # Add automatic correlation info to the response
        correlated_response = RequestResponse[RequestInfoMessage, Any].with_correlation(
            response,
            request.data,
            request.request_id,
        )

        if correlated_response.is_handled:
            logger.debug(
                f"Executor {self.id}'s interceptor handled request {request.request_id} "
                f"of type {type(request.data).__name__} from sub-workflow {request.sub_workflow_id}. "
                f"Sending response back to sub-workflow."
            )
            # Send response back to sub-workflow that made the request
            await ctx.send_message(
                SubWorkflowResponse(
                    request_id=request.request_id,
                    data=correlated_response.data,
                ),
                target_id=request.sub_workflow_id,
            )
        else:
            logger.debug(
                f"Executor {self.id}'s interceptor did not handle request {request.request_id} "
                f"of type {type(request.data).__name__} from sub-workflow {request.sub_workflow_id}. "
                "Forwarding to RequestInfoExecutor for external handling."
            )
            # Forward the request with potentially modified data
            # Update the data if interceptor provided a modified request
            if correlated_response.forward_request:
                request.data = correlated_response.forward_request

            # Send the inner request to RequestInfoExecutor to create external request
            await ctx.send_message(request)

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
        if message_type is SubWorkflowRequestInfo:
            raise ValueError(
                f"Executor {self.__class__.__name__} cannot define a handler for "
                "SubWorkflowRequestInfo directly. "
                f"Use @intercepts_request decorator to intercept sub-workflow requests."
            )

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

    @property
    def request_types(self) -> list[type[Any]]:
        """Get the list of request types that this executor can intercept via @intercepts_request.

        Returns:
            A list of the request types that this executor's interceptors can handle.
        """
        request_types: list[type[Any]] = []

        for request_type in self._request_interceptors:
            if isinstance(request_type, type):
                request_types.append(request_type)

        return request_types


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


TRequest = TypeVar("TRequest", bound="RequestInfoMessage")
TResponse = TypeVar("TResponse")


@dataclass
class RequestResponse(Generic[TRequest, TResponse]):
    """Response from @intercepts_request methods with automatic correlation support.

    This type allows intercepting executors to indicate whether they handled
    a request or whether it should be forwarded to external sources. When handled,
    the framework automatically adds correlation info to link responses to requests.
    """

    is_handled: bool
    data: TResponse | None = None
    forward_request: TRequest | None = None
    original_request: TRequest | None = None  # Added for automatic correlation
    request_id: str | None = None  # Added for tracking

    @classmethod
    def handled(cls, data: TResponse) -> "RequestResponse[TRequest, TResponse]":
        """Create a response indicating the request was handled.

        Correlation info (original_request, request_id) will be added automatically
        by the framework when processing intercepted requests.
        """
        return cls(is_handled=True, data=data)

    @classmethod
    def forward(cls, modified_request: Any = None) -> "RequestResponse[TRequest, TResponse]":
        """Create a response indicating the request should be forwarded."""
        return cls(is_handled=False, forward_request=modified_request)

    @staticmethod
    def with_correlation(
        original_response: "RequestResponse[TRequest, TResponse]",
        original_request: TRequest,
        request_id: str,
    ) -> "RequestResponse[TRequest, TResponse]":
        """Add correlation info to a response.

        This is called automatically by the framework when processing intercepted requests.
        """
        return RequestResponse(
            is_handled=original_response.is_handled,
            data=original_response.data,
            forward_request=original_response.forward_request,
            original_request=original_request,
            request_id=request_id,
        )


@dataclass
class SubWorkflowRequestInfo:
    """Routes requests from sub-workflows to parent workflows.

    This message type wraps requests from sub-workflows to add routing context,
    allowing parent workflows to intercept and potentially handle the request.
    """

    request_id: str  # Original request ID from sub-workflow
    sub_workflow_id: str  # ID of the WorkflowExecutor that sent this
    data: RequestInfoMessage  # The actual request data


@dataclass
class SubWorkflowResponse:
    """Routes responses back to sub-workflows.

    This message type is used to send responses back to sub-workflows that
    made requests, ensuring the response reaches the correct sub-workflow.
    """

    request_id: str  # Matches the original request ID
    data: Any  # The actual response data


# endregion: Request/Response Types

# region Intercepts Request Decorator

# TypeVar for request type that must be a RequestInfoMessage subclass
RequestInfoMessageT = TypeVar("RequestInfoMessageT", bound="RequestInfoMessage")


@overload
def intercepts_request(
    func: Callable[
        [Any, RequestInfoMessageT, WorkflowContext[Any, Any]], Awaitable[RequestResponse[RequestInfoMessageT, Any]]
    ],
) -> Callable[
    [Any, RequestInfoMessageT, WorkflowContext[Any, Any]], Awaitable[RequestResponse[RequestInfoMessageT, Any]]
]: ...


@overload
def intercepts_request(
    *,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None,
) -> Callable[
    [
        Callable[
            [Any, RequestInfoMessageT, WorkflowContext[Any, Any]], Awaitable[RequestResponse[RequestInfoMessageT, Any]]
        ]
    ],
    Callable[
        [Any, RequestInfoMessageT, WorkflowContext[Any, Any]], Awaitable[RequestResponse[RequestInfoMessageT, Any]]
    ],
]: ...


def intercepts_request(
    func: Callable[..., Any] | None = None,
    *,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None,
) -> Callable[..., Any]:
    """Decorator to mark methods that intercept sub-workflow requests.

    The request type is automatically inferred from the method's second parameter type hint.
    The type must be a subclass of RequestInfoMessage.

    This decorator allows executors in parent workflows to intercept and handle requests from
    sub-workflows before they are sent to external sources.

    Args:
        func: The function being decorated (automatically passed when used without parentheses).
        from_workflow: Optional ID of specific sub-workflow to intercept from.
        condition: Optional callable that must return True for interception.

    Returns:
        The decorated function with interception metadata.

    Example:
        @intercepts_request
        async def check_domain(
            self, request: DomainCheckRequest, ctx: WorkflowContext
        ) -> RequestResponse[DomainCheckRequest, bool]:
            # Type automatically inferred as DomainCheckRequest from parameter annotation
            if request.domain in self.approved_domains:
                return RequestResponse.handled(True)
            return RequestResponse.forward()

        @intercepts_request(from_workflow="email_validator")
        async def handle_specific(
            self, request: EmailRequest, ctx: WorkflowContext
        ) -> RequestResponse[EmailRequest, str]:
            # Only intercepts EmailRequest from the "email_validator" workflow
            return RequestResponse.handled("handled by parent")
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Extract request type from method signature
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) < 2:
            raise ValueError(f"Interceptor method '{func.__name__}' must have at least 2 parameters (self, request)")

        request_param = params[1]  # Second parameter (after self)
        request_type = request_param.annotation

        if request_type is inspect.Parameter.empty:
            raise ValueError(f"Interceptor method '{func.__name__}' request parameter must have a type annotation")

        # Runtime validation that it's a RequestInfoMessage subclass
        if isinstance(request_type, type):
            # We need to check if RequestInfoMessage is defined yet, since this runs at import time
            try:
                # Try to get RequestInfoMessage from the current module's globals
                request_info_message_class = None
                func_module = inspect.getmodule(func)
                if func_module and hasattr(func_module, "RequestInfoMessage"):
                    request_info_message_class = func_module.RequestInfoMessage
                else:
                    # Look in the current module (where this decorator is defined)
                    import sys

                    current_module = sys.modules[__name__]
                    if hasattr(current_module, "RequestInfoMessage"):
                        request_info_message_class = current_module.RequestInfoMessage

                if request_info_message_class and not issubclass(request_type, request_info_message_class):
                    raise TypeError(
                        f"Interceptor method '{func.__name__}' can only handle RequestInfoMessage subclasses, "
                        f"got {request_type}. Make sure your request type inherits from RequestInfoMessage."
                    )
            except (AttributeError, NameError):
                # RequestInfoMessage might not be defined yet at import time, skip validation
                # This will be caught later when the interceptor is actually called
                pass

        @functools.wraps(func)
        async def wrapper(self: Any, request: RequestInfoMessage, ctx: WorkflowContext[Any, Any]) -> Any:
            return await func(self, request, ctx)

        # Add metadata for discovery - store the inferred type
        wrapper._intercepts_request = request_type  # type: ignore
        wrapper._from_workflow = from_workflow  # type: ignore
        wrapper._intercept_condition = condition  # type: ignore

        return wrapper

    # If func is provided, we're being called without parentheses: @intercepts_request
    if func is not None:
        return decorator(func)

    # Otherwise, we're being called with parentheses: @intercepts_request(from_workflow="...")
    return decorator


# endregion: Intercepts Request Decorator

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
        self._sub_workflow_contexts: dict[str, dict[str, str]] = {}

    @handler
    async def run(self, message: RequestInfoMessage, ctx: WorkflowContext) -> None:
        """Run the RequestInfoExecutor with the given message."""
        source_executor_id = ctx.get_source_executor_id()

        event = RequestInfoEvent(
            request_id=message.request_id,
            source_executor_id=source_executor_id,
            request_type=type(message),
            request_data=message,
        )
        self._request_events[message.request_id] = event
        await self._record_pending_request_snapshot(message, source_executor_id, ctx)
        await ctx.add_event(event)

    @handler
    async def handle_sub_workflow_request(
        self,
        message: SubWorkflowRequestInfo,
        ctx: WorkflowContext,
    ) -> None:
        """Handle forwarded sub-workflow request.

        This method handles requests that were forwarded from parent workflows
        because they couldn't be handled locally.
        """
        # When called directly from runner, we need to use the sub_workflow_id as the source
        source_executor_id = message.sub_workflow_id

        # Store context for routing response back
        self._sub_workflow_contexts[message.request_id] = {
            "sub_workflow_id": message.sub_workflow_id,
            "parent_executor_id": source_executor_id,
        }

        # Create event for external handling - preserve the SubWorkflowRequestInfo wrapper
        event = RequestInfoEvent(
            request_id=message.request_id,  # Use original request ID
            source_executor_id=source_executor_id,
            request_type=type(message.data),  # Type of the wrapped data # type: ignore
            request_data=message.data,  # The wrapped request data
        )
        self._request_events[message.request_id] = event
        await ctx.add_event(event)

    async def handle_response(
        self,
        response_data: Any,
        request_id: str,
        ctx: WorkflowContext[SubWorkflowResponse | RequestResponse[RequestInfoMessage, Any]],
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

        # Check if this was a forwarded sub-workflow request
        if request_id in self._sub_workflow_contexts:
            context = self._sub_workflow_contexts.pop(request_id)

            # Send back to sub-workflow that made the original request
            await ctx.send_message(
                SubWorkflowResponse(
                    request_id=request_id,
                    data=response_data,
                ),
                target_id=context["sub_workflow_id"],
            )
        else:
            # Regular response - send directly back to source
            # Create a correlated response that includes both the response data and original request
            if not isinstance(event.data, RequestInfoMessage):
                raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
            correlated_response = RequestResponse[RequestInfoMessage, Any].handled(response_data)
            correlated_response = RequestResponse[RequestInfoMessage, Any].with_correlation(
                correlated_response,
                event.data,
                request_id,
            )

            await ctx.send_message(correlated_response, target_id=event.source_executor_id)

        await self._clear_pending_request_snapshot(request_id, ctx)

    def _register_instance_handler(
        self,
        name: str,
        func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]],
        message_type: type,
        ctx_annotation: Any,
        output_types: list[type],
        workflow_output_types: list[type],
    ) -> None:
        raise NotImplementedError("Cannot register handlers on RequestInfoExecutor")

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

    async def _clear_pending_request_snapshot(self, request_id: str, ctx: WorkflowContext[Any]) -> None:
        pending = await self._load_pending_request_state(ctx)
        if request_id not in pending:
            return

        pending.pop(request_id, None)
        await self._persist_pending_request_state(pending, ctx)

    async def _load_pending_request_state(self, ctx: WorkflowContext[Any]) -> dict[str, Any]:
        try:
            existing = await ctx.get_shared_state(self._PENDING_SHARED_STATE_KEY)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read pending request state: {exc}")
            return {}

        if not isinstance(existing, dict) or existing is None:
            if existing not in (None, {}):
                logger.warning(
                    f"RequestInfoExecutor {self.id} encountered non-dict pending state "
                    f"({type(existing).__name__}); resetting."
                )
            return {}

        return dict(existing)

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

        model_dump = getattr(request, "model_dump", None)
        if callable(model_dump):
            try:
                dump = self._make_json_safe(model_dump(mode="json"))
            except TypeError:
                dump = self._make_json_safe(model_dump())
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
            for key, val in value.items():
                safe_dict[str(key)] = self._make_json_safe(val)
            return safe_dict
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._make_json_safe(item) for item in value]
        return repr(value)

    async def has_pending_request(self, request_id: str, ctx: WorkflowContext[Any]) -> bool:
        if request_id in self._request_events or request_id in self._sub_workflow_contexts:
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
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read shared pending state during rehydrate: {exc}")
            shared_pending = None

        if isinstance(shared_pending, dict):
            for key, value in shared_pending.items():
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
                for key, value in state_pending.items():
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
            model_validate = getattr(request_cls, "model_validate", None)
            if callable(model_validate):
                return cast(RequestInfoMessage, model_validate(details))
        except (TypeError, ValueError) as exc:
            logger.debug(
                f"RequestInfoExecutor {self.id} validation failed for {request_cls.__name__} via model_validate: {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"RequestInfoExecutor {self.id} encountered unexpected error during "
                f"{request_cls.__name__}.model_validate: {exc}"
            )

        if is_dataclass(request_cls):
            try:
                field_names = {f.name for f in fields(request_cls)}
                ctor_kwargs = {name: details[name] for name in field_names if name in details}
                return request_cls(**ctor_kwargs)  # type: ignore[call-arg]
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
            instance = request_cls()  # type: ignore[call-arg]
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
            for request_id, snapshot in shared_map.items():
                RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)

        for state in checkpoint.executor_states.values():
            if not isinstance(state, Mapping):
                continue
            inner = state.get("pending_requests")
            if isinstance(inner, Mapping):
                for request_id, snapshot in inner.items():
                    RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)

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
            prompt=snapshot.get("prompt"),
            draft=snapshot.get("draft"),
            iteration=snapshot.get("iteration"),
            source_executor_id=snapshot.get("source_executor_id"),
        )

        extra = snapshot.get("details")
        if isinstance(extra, Mapping):
            RequestInfoExecutor._apply_update(
                details,
                prompt=extra.get("prompt"),
                draft=extra.get("draft"),
                iteration=extra.get("iteration"),
            )

    @staticmethod
    def _merge_message_payload(
        pending: dict[str, PendingRequestDetails],
        payload: Any,
        raw_message: Mapping[str, Any],
    ) -> None:
        if isinstance(payload, RequestResponse):
            request_id = payload.request_id or RequestInfoExecutor._get_field(payload.original_request, "request_id")
            if not request_id:
                return
            details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
            RequestInfoExecutor._apply_update(
                details,
                prompt=RequestInfoExecutor._get_field(payload.original_request, "prompt"),
                draft=RequestInfoExecutor._get_field(payload.original_request, "draft"),
                iteration=RequestInfoExecutor._get_field(payload.original_request, "iteration"),
                source_executor_id=raw_message.get("source_id"),
                original_request=payload.original_request,
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
            return obj.get(key)
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
