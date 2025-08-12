# Copyright (c) Microsoft. All rights reserved.

import functools
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar, overload

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
        self._id = id or str(uuid.uuid4())

        self._handlers: dict[type, Callable[[Any, WorkflowContext], Any]] = {}
        self._discover_handlers()

        if not self._handlers:
            raise ValueError(
                f"Executor {self.__class__.__name__} has no handlers defined. "
                "Please define at least one handler using the @handler decorator."
            )

    async def execute(self, message: Any, context: WorkflowContext) -> None:
        """Execute the executor with a given message and context.

        Args:
            message: The message to be processed by the executor.
            context: The workflow context in which the executor operates.

        Returns:
            An awaitable that resolves to the result of the execution.
        """
        handler: Callable[[Any, WorkflowContext], Any] | None = None
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
        """Discover message handlers in the executor class."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr) and hasattr(attr, "_handler_spec"):
                handler_spec = attr._handler_spec  # type: ignore
                if self._handlers.get(handler_spec["message_type"]) is not None:
                    raise ValueError(
                        f"Duplicate handler for type {handler_spec['message_type']} in {self.__class__.__name__}"
                    )
                self._handlers[handler_spec["message_type"]] = attr

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
    func: Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]],
) -> Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]]: ...


@overload
def handler(
    func: None = None,
    *,
    output_types: list[type] | None = None,
) -> Callable[
    [Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]]],
    Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]],
]: ...


def handler(
    func: Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]] | None = None,
    *,
    output_types: list[type] | None = None,
) -> (
    Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]]
    | Callable[
        [Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]]],
        Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]],
    ]
):
    """Decorator to register a handler for an executor.

    Args:
        func: The function to decorate. Can be None when using with parameters.
        output_types: Optional list of message types this handler can emit.

    Returns:
        The decorated function with handler metadata.

    Example:
        @handler
        async def handle_string(self, message: str, ctx: WorkflowContext) -> None:
            ...

        @handler(output_types=[str, int])
        async def handle_data(self, message: dict, ctx: WorkflowContext) -> None:
            ...
    """

    def decorator(
        func: Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]],
    ) -> Callable[[ExecutorT, Any, WorkflowContext], Awaitable[Any]]:
        # Extract the message type from a handler function.
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) != 3:  # self, message, ctx
            raise ValueError(f"Handler must have exactly 3 parameters, got {len(params)}")

        message_type = params[1].annotation
        if message_type is inspect.Parameter.empty:
            raise ValueError("Handler's second parameter must have a type annotation")

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, message: Any, ctx: WorkflowContext) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, message, ctx)

        wrapper._handler_spec = {  # type: ignore
            "name": func.__name__,
            "message_type": message_type,
            "output_types": output_types or [],
        }

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


# endregion: Handler Decorator

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

    @handler(output_types=[AgentExecutorResponse])
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext) -> None:
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

    request_id: str = str(uuid.uuid4())


class RequestInfoExecutor(Executor):
    """Built-in executor that handles request/response patterns in workflows.

    This executor acts as a gateway for external information requests. When it receives
    a request message, it saves the request details and emits a RequestInfoEvent. When
    a response is provided externally, it emits the response as a message.
    """

    # Well-known ID for the request info executor
    EXECUTOR_ID: ClassVar[str] = "request_info"

    def __init__(self):
        """Initialize the RequestInfoExecutor with its well-known ID."""
        super().__init__(id=self.EXECUTOR_ID)
        self._request_events: dict[str, RequestInfoEvent] = {}

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
        await ctx.add_event(event)

    async def handle_response(
        self,
        response_data: Any,
        request_id: str,
        ctx: WorkflowContext,
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
        await ctx.send_message(response_data, target_id=event.source_executor_id)


# endregion: Request Info Executor
