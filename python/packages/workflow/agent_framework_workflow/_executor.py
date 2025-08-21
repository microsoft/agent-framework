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

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, AgentThread, AIAgent, ChatMessage

from ._events import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    ExecutorCompletedEvent,
    ExecutorInvokeEvent,
    RequestInfoEvent,
)
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext

# region Executor


class Executor:
    """An executor is a component that processes messages in a workflow."""

    def __init__(self, id: str | None = None) -> None:
        """Initialize the executor with a unique identifier.

        Args:
            id: A unique identifier for the executor. If None, a new UUID will be generated.
        """
        self._id = id or f"{self.__class__.__name__}/{uuid.uuid4()}"

        self._handlers: dict[type, Callable[[Any, WorkflowContext[Any]], Any]] = {}
        self._request_interceptors: dict[type | str, list[dict[str, Any]]] = {}
        self._discover_handlers()

        if not self._handlers:
            raise ValueError(
                f"Executor {self.__class__.__name__} has no handlers defined. "
                "Please define at least one handler using the @handler decorator."
            )

    async def execute(self, message: Any, context: WorkflowContext[Any]) -> None:
        """Execute the executor with a given message and context.

        Args:
            message: The message to be processed by the executor.
            context: The workflow context in which the executor operates.

        Returns:
            An awaitable that resolves to the result of the execution.
        """
        # Lazy registration for SubWorkflowRequestInfo if we have interceptors
        if self._request_interceptors and message.__class__.__name__ == "SubWorkflowRequestInfo":
            # Directly handle SubWorkflowRequestInfo
            await context.add_event(ExecutorInvokeEvent(self.id))
            await self._handle_sub_workflow_request(message, context)
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
        await handler(message, context)
        await context.add_event(ExecutorCompletedEvent(self.id))

    @property
    def id(self) -> str:
        """Get the unique identifier of the executor."""
        return self._id

    def _discover_handlers(self) -> None:
        """Discover message handlers and request interceptors in the executor class."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr):
                # Discover @handler methods and @intercepts_request methods
                if hasattr(attr, "_handler_spec"):
                    handler_spec = attr._handler_spec  # type: ignore
                    message_type = handler_spec["message_type"]

                    # Handle generic RequestResponse types by using the origin type for isinstance checks
                    from typing import get_origin

                    origin_type = get_origin(message_type)
                    if (
                        origin_type is not None
                        and hasattr(origin_type, "__name__")
                        and origin_type.__name__ == "RequestResponse"
                    ):
                        # Use the base RequestResponse type instead of RequestResponse[T, U] for compatibility
                        message_type = origin_type

                    if self._handlers.get(message_type) is not None:
                        raise ValueError(f"Duplicate handler for type {message_type} in {self.__class__.__name__}")
                    self._handlers[message_type] = attr

                # Discover @intercepts_request methods
                if hasattr(attr, "_intercepts_request"):
                    interceptor_info = {
                        "method": attr,
                        "from_workflow": getattr(attr, "_from_workflow", None),
                        "condition": getattr(attr, "_intercept_condition", None),
                    }
                    request_type = attr._intercepts_request  # type: ignore
                    if request_type not in self._request_interceptors:
                        self._request_interceptors[request_type] = []
                    self._request_interceptors[request_type].append(interceptor_info)

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
            if isinstance(request_type, type) and isinstance(request.data, request_type):
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
                        correlated_response = RequestResponse._with_correlation(
                            response, request.data, request.request_id
                        )

                        if correlated_response.is_handled:
                            # Send response back to sub-workflow
                            from ._runner_context import Message

                            response_message = Message(
                                source_id=self.id,
                                target_id=request.sub_workflow_id,
                                data=SubWorkflowResponse(
                                    request_id=request.request_id,
                                    data=correlated_response.data,
                                ),
                            )
                            await ctx.send_message(response_message)
                        else:
                            # Forward WITH CONTEXT PRESERVED
                            # Update the data if interceptor provided a modified request
                            if correlated_response.forward_request:
                                request.data = correlated_response.forward_request

                            # Send the inner request to RequestInfoExecutor to create external request
                            from ._runner_context import Message

                            forward_message = Message(
                                source_id=self.id,
                                data=request,
                            )
                            await ctx.send_message(forward_message)
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
        from ._runner_context import Message

        passthrough_message = Message(source_id=self.id, data=request.data)
        await ctx.send_message(passthrough_message)

    def can_handle(self, message: Any) -> bool:
        """Check if the executor can handle a given message type.

        Args:
            message: The message to check.

        Returns:
            True if the executor can handle the message type, False otherwise.
        """
        return any(is_instance_of(message, message_type) for message_type in self._handlers)


# endregion: Executor

# region Handler Decorator


ExecutorT = TypeVar("ExecutorT", bound="Executor")


@overload
def handler(
    func: Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]],
) -> Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]]: ...


@overload
def handler(
    func: None = None,
) -> Callable[
    [Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]]],
    Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]],
]: ...


def handler(
    func: Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[Any]] | None = None,
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
        with contextlib.suppress(Exception):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._handler_spec = {  # type: ignore
            "name": func.__name__,
            "message_type": message_type,
            # Keep output_types in spec for validators, inferred from WorkflowContext[T]
            "output_types": inferred_output_types,
        }

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


# endregion: Handler Decorator

# region Request/Response Types

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
    def handled(cls, data: TResponse) -> "RequestResponse[Any, TResponse]":
        """Create a response indicating the request was handled.

        Correlation info (original_request, request_id) will be added automatically
        by the framework when processing intercepted requests.
        """
        return cls(is_handled=True, data=data)

    @classmethod
    def forward(cls, modified_request: Any = None) -> "RequestResponse[Any, Any]":
        """Create a response indicating the request should be forwarded."""
        return cls(is_handled=False, forward_request=modified_request)

    @staticmethod
    def _with_correlation(
        original_response: "RequestResponse[Any, TResponse]", original_request: TRequest, request_id: str
    ) -> "RequestResponse[TRequest, TResponse]":
        """Internal method to add correlation info to a response.

        This is called automatically by the framework and should not be used directly.
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
    data: Any  # The actual request data


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


@overload
def intercepts_request(
    request_type: type | str,
) -> Callable[
    [Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]]],
    Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]],
]: ...


@overload
def intercepts_request(
    request_type: type | str,
    *,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None,
) -> Callable[
    [Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]]],
    Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]],
]: ...


def intercepts_request(
    request_type: type | str,
    *,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None,
) -> Callable[
    [Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]]],
    Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]],
]:
    """Decorator to mark methods that intercept sub-workflow requests.

    This decorator allows the executor in the parent workflows to intercept and handle requests from
    sub-workflows before they are sent to external sources.

    Args:
        request_type: The type of request to intercept (can be a class or string).
        from_workflow: Optional ID of specific sub-workflow to intercept from.
        condition: Optional callable that must return True for interception.

    Returns:
        The decorated function with interception metadata.

    Example:
        @intercepts_request(DomainCheckRequest)
        async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> RequestResponse:
            if request.domain in self.approved_domains:
                return RequestResponse.handled(True)
            return RequestResponse.forward()
    """

    def decorator(
        func: Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]],
    ) -> Callable[[ExecutorT, Any, WorkflowContext[Any]], Awaitable[RequestResponse[Any, Any]]]:
        @functools.wraps(func)
        async def wrapper(self: ExecutorT, request: Any, ctx: WorkflowContext[Any]) -> RequestResponse[Any, Any]:
            return await func(self, request, ctx)

        # Add metadata for discovery
        wrapper._intercepts_request = request_type  # type: ignore
        wrapper._from_workflow = from_workflow  # type: ignore
        wrapper._intercept_condition = condition  # type: ignore

        return wrapper

    return decorator


# endregion: Intercepts Request Decorator

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
        response: The agent run response containing the messages generated by the agent.
    """

    executor_id: str
    agent_run_response: AgentRunResponse


class AgentExecutor(Executor):
    """built-in executor that wraps an agent for handling messages."""

    def __init__(
        self,
        agent: AIAgent,
        *,
        agent_thread: AgentThread | None = None,
        streaming: bool = False,
        id: str | None = None,
    ):
        """Initialize the executor with a unique identifier.

        Args:
            agent: The agent to be wrapped by this executor.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            streaming: Whether to enable streaming for the agent. If enabled, the executor will emit
                AgentRunStreamingEvent updates instead of a single AgentRunEvent.
            id: A unique identifier for the executor. If None, a new UUID will be generated.
        """
        super().__init__(id or agent.id)
        self._agent = agent
        self._agent_thread = agent_thread or self._agent.get_new_thread()
        self._streaming = streaming
        self._cache: list[ChatMessage] = []

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Run the agent executor with the given request."""
        self._cache.extend(request.messages)

        if request.should_respond:
            if self._streaming:
                updates: list[AgentRunResponseUpdate] = []
                async for update in self._agent.run_streaming(
                    self._cache,
                    thread=self._agent_thread,
                ):
                    updates.append(update)
                    await ctx.add_event(AgentRunStreamingEvent(self.id, update))
                response = AgentRunResponse.from_agent_run_response_updates(updates)
            else:
                response = await self._agent.run(
                    self._cache,
                    thread=self._agent_thread,
                )
                await ctx.add_event(AgentRunEvent(self.id, response))

            await ctx.send_message(AgentExecutorResponse(self.id, response))
            self._cache.clear()


# endregion: Agent Executor


# region Request Info Executor


@dataclass
class RequestInfoMessage:
    """Base class for all request messages in workflows.

    Any message that should be routed to the RequestInfoExecutor for external
    handling must inherit from this class. This ensures type safety and makes
    the request/response pattern explicit.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# Note: SubWorkflowRequestInfo, SubWorkflowResponse, and RequestResponse
# have been moved before intercepts_request decorator


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
            request_type=type(message.data),  # SubWorkflowRequestInfo type
            request_data=message.data,  # The full SubWorkflowRequestInfo
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
            correlated_response = RequestResponse.handled(response_data)
            correlated_response = RequestResponse._with_correlation(correlated_response, event.data, request_id)

            await ctx.send_message(correlated_response, target_id=event.source_executor_id)


# endregion: Request Info Executor

# region Workflow Executor


class WorkflowExecutor(Executor):
    """An executor that runs another workflow as its execution logic.

    This executor wraps a workflow to make it behave as an executor, enabling
    hierarchical workflow composition. Sub-workflows can send requests that
    are intercepted by parent workflows.
    """

    def __init__(self, workflow: "Workflow", id: str | None = None):
        """Initialize the WorkflowExecutor.

        Args:
            workflow: The workflow to execute as a sub-workflow.
            id: Optional unique identifier for this executor.
        """
        super().__init__(id)
        self._workflow = workflow
        # Track pending external responses by request_id
        self._pending_responses: dict[str, Any] = {}  # request_id -> response_data
        # Track workflow state for proper resumption - support multiple concurrent requests
        self._pending_requests: dict[str, Any] = {}  # request_id -> original request data
        self._active_executions: int = 0  # Count of active sub-workflow executions

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
            events = [event async for event in self._workflow.run_streaming(input_data)]

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
                    wrapped_request = SubWorkflowRequestInfo(
                        request_id=event.request_id,
                        sub_workflow_id=self.id,
                        data=event.data,
                    )

                    await ctx.send_message(wrapped_request)
                    # Exit and wait for response - sub-workflow is paused
                    return

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

        This handler receives responses and sends them to the sub-workflow,
        then continues the sub-workflow execution to completion.

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

        from ._events import WorkflowCompletedEvent

        # Send responses to the sub-workflow and continue execution until completion
        result_events = [
            event async for event in self._workflow.send_responses_streaming({response.request_id: response.data})
        ]

        # Find the completion event and send result to parent
        for event in result_events:
            if isinstance(event, WorkflowCompletedEvent):
                await ctx.send_message(event.data)
                self._active_executions -= 1
                return


# endregion: Workflow Executor
