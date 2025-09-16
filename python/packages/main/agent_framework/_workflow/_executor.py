# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import UnionType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union, get_args, get_origin, overload

if TYPE_CHECKING:
    from ._workflow import Workflow

from pydantic import Field

from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, AgentThread, ChatMessage
from agent_framework._pydantic import AFBaseModel

from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,
    ExecutorCompletedEvent,
    ExecutorInvokeEvent,
    RequestInfoEvent,
)
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext

# region Executor


class Executor(AFBaseModel):
    """An executor is a component that processes messages in a workflow."""

    # Provide a default so static analyzers (e.g., pyright) don't require passing `id`.
    # Runtime still sets a concrete value in __init__.
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        min_length=1,
        description="Unique identifier for the executor",
    )
    type_: str = Field(default="", alias="type", description="The type of executor, corresponding to the class name")

    def __init__(self, id: str | None = None, **kwargs: Any) -> None:
        """Initialize the executor with a unique identifier.

        Args:
            id: A unique identifier for the executor. If None, a new ID will be generated
                following the format <class_name>/<uuid>.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        executor_id = f"{self.__class__.__name__}/{uuid.uuid4()}" if id is None else id

        kwargs.update({"id": executor_id})
        if "type" not in kwargs and "type_" not in kwargs:
            kwargs["type_"] = self.__class__.__name__

        super().__init__(**kwargs)

        self._handlers: dict[type, Callable[[Any, WorkflowContext[Any]], Any]] = {}
        self._request_interceptors: dict[type | str, list[dict[str, Any]]] = {}
        self._instance_handler_specs: list[dict[str, Any]] = []
        self._discover_handlers()

        if not self._handlers and not self._request_interceptors:
            raise ValueError(
                f"Executor {self.__class__.__name__} has no handlers defined. "
                "Please define at least one handler using the @handler decorator "
                "or @intercepts_request decorator."
            )

    async def execute(self, message: Any, context: WorkflowContext[Any]) -> None:
        """Execute the executor with a given message and context.

        Args:
            message: The message to be processed by the executor.
            context: The workflow context in which the executor operates.

        Returns:
            An awaitable that resolves to the result of the execution.
        """
        # Create processing span for tracing (gracefully handles disabled tracing)
        from ._telemetry import workflow_tracer

        source_trace_contexts = getattr(context, "_trace_contexts", None)
        source_span_ids = getattr(context, "_source_span_ids", None)

        # Handle case where Message wrapper is passed instead of raw data
        from ._runner_context import Message

        if isinstance(message, Message):
            message = message.data

        with workflow_tracer.create_processing_span(
            self.id,
            self.__class__.__name__,
            type(message).__name__,
            source_trace_contexts=source_trace_contexts,
            source_span_ids=source_span_ids,
        ):
            # Lazy registration for SubWorkflowRequestInfo if we have interceptors
            if self._request_interceptors and message.__class__.__name__ == "SubWorkflowRequestInfo":
                # Directly handle SubWorkflowRequestInfo
                await context.add_event(ExecutorInvokeEvent(self.id))
                try:
                    await self._handle_sub_workflow_request(message, context)
                except Exception as exc:
                    # Surface structured executor failure before propagating
                    from ._events import ExecutorFailedEvent, WorkflowErrorDetails

                    await context.add_event(ExecutorFailedEvent(self.id, WorkflowErrorDetails.from_exception(exc)))
                    raise
                await context.add_event(ExecutorCompletedEvent(self.id))
                return

            handler: Callable[[Any, WorkflowContext[Any]], Any] | None = None
            for message_type in self._handlers:
                if is_instance_of(message, message_type):
                    handler = self._handlers[message_type]
                    break

            if handler is None:
                raise RuntimeError(f"Executor {self.__class__.__name__} cannot handle message of type {type(message)}.")
            await context.add_event(ExecutorInvokeEvent(self.id))
            try:
                await handler(message, context)
            except Exception as exc:
                # Surface structured executor failure before propagating
                from ._events import ExecutorFailedEvent, WorkflowErrorDetails

                await context.add_event(ExecutorFailedEvent(self.id, WorkflowErrorDetails.from_exception(exc)))
                raise
            await context.add_event(ExecutorCompletedEvent(self.id))

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
                        # Get the bound method
                        bound_method = getattr(self, attr_name)
                        self._handlers[message_type] = bound_method

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
            except AttributeError:
                # Skip attributes that may not be accessible
                continue

    def _register_sub_workflow_handler(self) -> None:
        """Register automatic handler for SubWorkflowRequestInfo messages."""
        # We need to use a string reference until the class is defined
        # This will be resolved later when the class is actually used
        pass  # Will be registered lazily when needed

    async def _handle_sub_workflow_request(
        self,
        request: "SubWorkflowRequestInfo",
        ctx: WorkflowContext[Any],
    ) -> None:
        """Automatic routing to @intercepts_request methods.

        This is only active for executors that have @intercepts_request methods.
        """
        # Try to match against registered interceptors
        for request_type, interceptor_list in self._request_interceptors.items():
            matched = False

            # Check type matching
            if isinstance(request_type, type) and is_instance_of(request.data, request_type):
                matched = True
            elif (
                isinstance(request_type, str)
                and hasattr(request.data, "__class__")
                and request.data.__class__.__name__ == request_type
            ):
                # String matching - could check against type name or other attributes
                matched = True

            if matched:
                # Check each interceptor in the list for this request type
                for interceptor_info in interceptor_list:
                    # Check workflow scope if specified
                    from_workflow = interceptor_info["from_workflow"]
                    if from_workflow and request.sub_workflow_id != from_workflow:
                        continue  # Skip this interceptor, wrong workflow

                    # Check additional condition
                    condition = interceptor_info["condition"]
                    if condition and not condition(request):
                        continue

                    # Call the interceptor method
                    method = interceptor_info["method"]
                    response = await method(request.data, ctx)

                    # Check if interceptor handled it or needs to forward
                    if isinstance(response, RequestResponse):
                        # Add automatic correlation info to the response
                        correlated_response = RequestResponse[RequestInfoMessage, Any].with_correlation(
                            response,
                            request.data,
                            request.request_id,
                        )

                        if correlated_response.is_handled:
                            # Send response back to sub-workflow
                            await ctx.send_message(
                                SubWorkflowResponse(
                                    request_id=request.request_id,
                                    data=correlated_response.data,
                                ),
                                target_id=request.sub_workflow_id,
                            )
                        else:
                            # Forward WITH CONTEXT PRESERVED
                            # Update the data if interceptor provided a modified request
                            if correlated_response.forward_request:
                                request.data = correlated_response.forward_request

                            # Send the inner request to RequestInfoExecutor to create external request
                            await ctx.send_message(request)
                    else:
                        # Legacy support: direct return means handled
                        await ctx.send_message(
                            SubWorkflowResponse(
                                request_id=request.request_id,
                                data=response,
                            ),
                            target_id=request.sub_workflow_id,
                        )
                    return

        # No interceptor found - forward inner request to RequestInfoExecutor
        # This sends the original request to RequestInfoExecutor
        await ctx.send_message(request.data)

    def can_handle(self, message: Any) -> bool:
        """Check if the executor can handle a given message type.

        Args:
            message: The message to check.

        Returns:
            True if the executor can handle the message type, False otherwise.
        """
        return any(is_instance_of(message, message_type) for message_type in self._handlers)

    def register_instance_handler(
        self,
        name: str,
        func: Callable[[Any, WorkflowContext[Any]], Awaitable[Any]],
        message_type: type,
        ctx_annotation: Any,
        output_types: list[type],
    ) -> None:
        """Register a handler at instance level.

        Args:
            name: Name of the handler function for error reporting
            func: The async handler function to register
            message_type: Type of message this handler processes
            ctx_annotation: The WorkflowContext[T] annotation from the function
            output_types: List of output types inferred from ctx_annotation
        """
        if message_type in self._handlers:
            raise ValueError(f"Handler for type {message_type} already registered in {self.__class__.__name__}")

        self._handlers[message_type] = func
        self._instance_handler_specs.append({
            "name": name,
            "message_type": message_type,
            "ctx_annotation": ctx_annotation,
            "output_types": output_types,
        })

    def can_handle_type(self, message_type: type[Any]) -> bool:
        """Check if the executor can handle a given message type.

        Args:
            message_type: The message type to check.

        Returns:
            True if the executor can handle the message type, False otherwise.
        """
        return message_type in self._handlers


# endregion: Executor

# region Handler Decorator


ExecutorT = TypeVar("ExecutorT", bound="Executor")


def handler(
    func: Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]],
) -> (
    Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]]
    | Callable[
        [Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]]],
        Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]],
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

    def _infer_output_types_from_ctx_annotation(ctx_annotation: Any) -> list[type[Any]]:
        """Infer output types list from the WorkflowContext generic parameter.

        Examples:
        - WorkflowContext[str] -> [str]
        - WorkflowContext[str | int] -> [str, int]
        - WorkflowContext[Union[str, int]] -> [str, int]
        - WorkflowContext -> [] (unknown)
        """
        # If no annotation or not parameterized, return empty list
        try:
            origin = get_origin(ctx_annotation)
        except Exception:
            origin = None

        # If annotation is unsubscripted WorkflowContext, nothing to infer
        if origin is None:
            # Might be the class itself or Any; try simple check by name to avoid import cycles
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

    def decorator(
        func: Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]],
    ) -> Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]]:
        # Extract the message type from a handler function.
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) != 3:  # self, message, ctx
            raise ValueError(f"Handler must have exactly 3 parameters, got {len(params)}")

        message_type = params[1].annotation
        if message_type is inspect.Parameter.empty:
            raise ValueError("Handler's second parameter must have a type annotation")

        ctx_annotation = params[2].annotation
        if ctx_annotation is inspect.Parameter.empty:
            # Allow missing ctx annotation, but we can't infer outputs
            inferred_output_types: list[type[Any]] = []
        else:
            inferred_output_types = _infer_output_types_from_ctx_annotation(ctx_annotation)

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, message: Any, ctx: WorkflowContext[Any]) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, message, ctx)

        # Preserve the original function signature for introspection during validation
        with contextlib.suppress(AttributeError, TypeError):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._handler_spec = {  # type: ignore
            "name": func.__name__,
            "message_type": message_type,
            # Keep output_types in spec for validators, inferred from WorkflowContext[T]
            "output_types": inferred_output_types,
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

# Type alias for interceptor functions
InterceptorFunc = Callable[
    [Any, RequestInfoMessageT, WorkflowContext[Any]], Awaitable[RequestResponse[RequestInfoMessageT, Any]]
]


@overload
def intercepts_request(
    func: Callable[..., Any],
) -> Callable[..., Any]: ...


@overload
def intercepts_request(
    *,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


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
            self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
        ) -> RequestResponse[DomainCheckRequest, bool]:
            # Type automatically inferred as DomainCheckRequest from parameter annotation
            if request.domain in self.approved_domains:
                return RequestResponse.handled(True)
            return RequestResponse.forward()

        @intercepts_request(from_workflow="email_validator")
        async def handle_specific(
            self, request: EmailRequest, ctx: WorkflowContext[Any]
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
        async def wrapper(self: Any, request: Any, ctx: WorkflowContext[Any]) -> Any:
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

    def __init__(self, id: str | None = None):
        """Initialize the RequestInfoExecutor with an optional custom ID.

        Args:
            id: Optional custom ID for this RequestInfoExecutor. If not provided,
                a unique ID will be generated.
        """
        import uuid

        executor_id = id or f"request_info_{uuid.uuid4().hex[:8]}"
        super().__init__(id=executor_id)
        self._request_events: dict[str, RequestInfoEvent] = {}
        self._sub_workflow_contexts: dict[str, dict[str, str]] = {}

    @handler
    async def run(self, message: RequestInfoMessage, ctx: WorkflowContext[None]) -> None:
        """Run the RequestInfoExecutor with the given message."""
        source_executor_id = ctx.get_source_executor_id()

        event = RequestInfoEvent(
            request_id=message.request_id,
            source_executor_id=source_executor_id,
            request_type=type(message),
            request_data=message,
        )
        self._request_events[message.request_id] = event
        await ctx.add_event(event)

    @handler
    async def handle_sub_workflow_request(
        self,
        message: SubWorkflowRequestInfo,
        ctx: WorkflowContext[None],
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
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle a response to a request.

        Args:
            request_id: The ID of the request to which this response corresponds.
            response_data: The data returned in the response.
            ctx: The workflow context for sending the response.
        """
        if request_id not in self._request_events:
            raise ValueError(f"No request found with ID: {request_id}")

        event = self._request_events.pop(request_id)

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
            exec_id = str(agent_name) if agent_name else f"executor_{uuid.uuid4()}"
        super().__init__(exec_id)
        self._agent = agent
        self._agent_thread = agent_thread or self._agent.get_new_thread()
        self._streaming = streaming
        self._cache: list[ChatMessage] = []

    async def _run_agent_and_emit(self, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Execute the underlying agent, emit events, and enqueue response.

        Terminal detection & WorkflowCompletedEvent emission are handled centrally in Runner.
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


# region Workflow Executor


class WorkflowExecutor(Executor):
    """An executor that runs another workflow as its execution logic.

    This executor wraps a workflow to make it behave as an executor, enabling
    hierarchical workflow composition. Sub-workflows can send requests that
    are intercepted by parent workflows.
    """

    workflow: "Workflow" = Field(description="The workflow to execute as a sub-workflow")

    def __init__(self, workflow: "Workflow", id: str | None = None, **kwargs: Any):
        """Initialize the WorkflowExecutor.

        Args:
            workflow: The workflow to execute as a sub-workflow.
            id: Optional unique identifier for this executor.
            **kwargs: Additional keyword arguments passed to the parent constructor.
        """
        kwargs.update({"workflow": workflow})
        super().__init__(id, **kwargs)

        # Track pending external responses by request_id
        self._pending_responses: dict[str, Any] = {}  # request_id -> response_data
        # Track workflow state for proper resumption - support multiple concurrent requests
        self._pending_requests: dict[str, Any] = {}  # request_id -> original request data
        self._active_executions: int = 0  # Count of active sub-workflow executions
        # Response accumulation for multiple concurrent responses
        self._collected_responses: dict[str, Any] = {}  # Accumulate responses
        self._expected_response_count: int = 0  # Track how many responses we're waiting for

    @handler  # No output_types - can send any completion data type
    async def process_workflow(self, input_data: object, ctx: WorkflowContext[Any]) -> None:
        """Execute the sub-workflow with raw input data.

        This handler starts a new sub-workflow execution. When the sub-workflow
        needs external information, it pauses and sends a request to the parent.

        Args:
            input_data: The input data to send to the sub-workflow.
            ctx: The workflow context from the parent.
        """
        # Skip SubWorkflowResponse and SubWorkflowRequestInfo - they have specific handlers
        if isinstance(input_data, (SubWorkflowResponse, SubWorkflowRequestInfo)):
            return

        from ._events import RequestInfoEvent, WorkflowCompletedEvent

        # Track this execution
        self._active_executions += 1

        try:
            # Run the sub-workflow and collect all events
            events = [event async for event in self.workflow.run_stream(input_data)]

            # Count requests and initialize response tracking
            request_count = 0
            for event in events:
                if isinstance(event, RequestInfoEvent):
                    request_count += 1

            # Initialize response accumulation for this execution
            # For sequential workflows (like step_08), expect only current requests
            # For parallel workflows (like step_09), expect all requests at once
            self._expected_response_count = request_count
            self._collected_responses = {}

            # If no requests in initial run, handle completion immediately
            if request_count == 0:
                self._expected_response_count = 0

            # Process events to check for completion or requests
            for event in events:
                if isinstance(event, WorkflowCompletedEvent):
                    # Sub-workflow completed normally - send result to parent
                    await ctx.send_message(event.data)
                    self._active_executions -= 1
                    return  # Exit after completion

                if isinstance(event, RequestInfoEvent):
                    # Sub-workflow needs external information
                    # Track the pending request
                    self._pending_requests[event.request_id] = event.data

                    # Wrap request with routing context and send to parent
                    if not isinstance(event.data, RequestInfoMessage):
                        raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
                    wrapped_request = SubWorkflowRequestInfo(
                        request_id=event.request_id,
                        sub_workflow_id=self.id,
                        data=event.data,
                    )

                    await ctx.send_message(wrapped_request)
                    # Continue processing remaining events (no return)

        except Exception as e:
            from ._events import ExecutorEvent

            # Sub-workflow failed - create error event
            error_event = ExecutorEvent(executor_id=self.id, data={"error": str(e), "type": "sub_workflow_error"})
            await ctx.add_event(error_event)
            self._active_executions -= 1
            raise

    @handler
    async def handle_response(
        self,
        response: SubWorkflowResponse,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle response from parent for a forwarded request.

        This handler accumulates responses and only resumes the sub-workflow
        when all expected responses have been received.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        # Check if we have this pending request
        pending_requests = getattr(self, "_pending_requests", {})
        if response.request_id not in pending_requests:
            return

        # Remove the request from pending list
        pending_requests.pop(response.request_id, None)

        # Accumulate the response
        self._collected_responses[response.request_id] = response.data

        # Check if we have all expected responses for current batch
        if len(self._collected_responses) >= self._expected_response_count:
            from ._events import RequestInfoEvent, WorkflowCompletedEvent

            # Send all collected responses to the sub-workflow
            responses_to_send = dict(self._collected_responses)
            self._collected_responses.clear()  # Clear for next batch

            result_events = [event async for event in self.workflow.send_responses_streaming(responses_to_send)]

            # Process the result events
            new_request_count = 0
            for event in result_events:
                if isinstance(event, WorkflowCompletedEvent):
                    # Sub-workflow completed - send result to parent
                    await ctx.send_message(event.data)
                    self._active_executions -= 1
                    return
                if isinstance(event, RequestInfoEvent):
                    # Sub-workflow sent more requests - prepare for next batch
                    new_request_count += 1
                    self._pending_requests[event.request_id] = event.data

                    # Send the new request to parent
                    if not isinstance(event.data, RequestInfoMessage):
                        raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
                    wrapped_request = SubWorkflowRequestInfo(
                        request_id=event.request_id,
                        sub_workflow_id=self.id,
                        data=event.data,
                    )
                    await ctx.send_message(wrapped_request)

            # Update expected count for next batch of requests
            self._expected_response_count = new_request_count


# endregion: Workflow Executor
