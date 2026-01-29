# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, MutableSequence, Sequence
from enum import Enum
from functools import update_wrapper
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias, overload

from ._serialization import SerializationMixin
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ResponseStream,
    prepare_messages,
)
from .exceptions import MiddlewareException

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from pydantic import BaseModel

    from ._agents import AgentProtocol
    from ._clients import ChatClientProtocol
    from ._threads import AgentThread
    from ._tools import FunctionTool
    from ._types import ChatOptions, ChatResponse, ChatResponseUpdate

    TResponseModelT = TypeVar("TResponseModelT", bound=BaseModel)

__all__ = [
    "AgentMiddleware",
    "AgentMiddlewareMixin",
    "AgentMiddlewareTypes",
    "AgentRunContext",
    "ChatContext",
    "ChatMiddleware",
    "ChatMiddlewareMixin",
    "FunctionInvocationContext",
    "FunctionMiddleware",
    "Middleware",
    "agent_middleware",
    "chat_middleware",
    "function_middleware",
    "use_agent_middleware",
]

TAgent = TypeVar("TAgent", bound="AgentProtocol")
TContext = TypeVar("TContext")


class MiddlewareType(str, Enum):
    """Enum representing the type of middleware.

    Used internally to identify and categorize middleware types.
    """

    AGENT = "agent"
    FUNCTION = "function"
    CHAT = "chat"


class AgentRunContext(SerializationMixin):
    """Context object for agent middleware invocations.

    This context is passed through the agent middleware pipeline and contains all information
    about the agent invocation.

    Attributes:
        agent: The agent being invoked.
        messages: The messages being sent to the agent.
        thread: The agent thread for this invocation, if any.
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between agent middleware.
        result: Agent execution result. Can be observed after calling ``next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be AgentResponse.
                For streaming: should be AsyncIterable[AgentResponseUpdate].
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
        kwargs: Additional keyword arguments passed to the agent run method.

    Examples:
        .. code-block:: python

            from agent_framework import AgentMiddleware, AgentRunContext


            class LoggingMiddleware(AgentMiddleware):
                async def process(self, context: AgentRunContext, next):
                    print(f"Agent: {context.agent.name}")
                    print(f"Messages: {len(context.messages)}")
                    print(f"Thread: {context.thread}")
                    print(f"Streaming: {context.is_streaming}")

                    # Store metadata
                    context.metadata["start_time"] = time.time()

                    # Continue execution
                    await next(context)

                    # Access result after execution
                    print(f"Result: {context.result}")
    """

    INJECTABLE: ClassVar[set[str]] = {"agent", "thread", "result"}

    def __init__(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        thread: "AgentThread | None" = None,
        is_streaming: bool = False,
        metadata: dict[str, Any] | None = None,
        result: AgentResponse | AsyncIterable[AgentResponseUpdate] | None = None,
        terminate: bool = False,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the AgentRunContext.

        Args:
            agent: The agent being invoked.
            messages: The messages being sent to the agent.
            thread: The agent thread for this invocation, if any.
            is_streaming: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between agent middleware.
            result: Agent execution result.
            terminate: A flag indicating whether to terminate execution after current middleware.
            kwargs: Additional keyword arguments passed to the agent run method.
        """
        self.agent = agent
        self.messages = messages
        self.thread = thread
        self.is_streaming = is_streaming
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.terminate = terminate
        self.kwargs = kwargs if kwargs is not None else {}


class FunctionInvocationContext(SerializationMixin):
    """Context object for function middleware invocations.

    This context is passed through the function middleware pipeline and contains all information
    about the function invocation.

    Attributes:
        function: The function being invoked.
        arguments: The validated arguments for the function.
        metadata: Metadata dictionary for sharing data between function middleware.
        result: Function execution result. Can be observed after calling ``next()``
                to see the actual execution result or can be set to override the execution result.
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
        kwargs: Additional keyword arguments passed to the chat method that invoked this function.

    Examples:
        .. code-block:: python

            from agent_framework import FunctionMiddleware, FunctionInvocationContext


            class ValidationMiddleware(FunctionMiddleware):
                async def process(self, context: FunctionInvocationContext, next):
                    print(f"Function: {context.function.name}")
                    print(f"Arguments: {context.arguments}")

                    # Validate arguments
                    if not self.validate(context.arguments):
                        context.result = {"error": "Validation failed"}
                        context.terminate = True
                        return

                    # Continue execution
                    await next(context)
    """

    INJECTABLE: ClassVar[set[str]] = {"function", "arguments", "result"}

    def __init__(
        self,
        function: "FunctionTool[Any, Any]",
        arguments: "BaseModel",
        metadata: dict[str, Any] | None = None,
        result: Any = None,
        terminate: bool = False,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the FunctionInvocationContext.

        Args:
            function: The function being invoked.
            arguments: The validated arguments for the function.
            metadata: Metadata dictionary for sharing data between function middleware.
            result: Function execution result.
            terminate: A flag indicating whether to terminate execution after current middleware.
            kwargs: Additional keyword arguments passed to the chat method that invoked this function.
        """
        self.function = function
        self.arguments = arguments
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.terminate = terminate
        self.kwargs = kwargs if kwargs is not None else {}


class ChatContext(SerializationMixin):
    """Context object for chat middleware invocations.

    This context is passed through the chat middleware pipeline and contains all information
    about the chat request.

    Attributes:
        chat_client: The chat client being invoked.
        messages: The messages being sent to the chat client.
        options: The options for the chat request as a dict.
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between chat middleware.
        result: Chat execution result. Can be observed after calling ``next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be ChatResponse.
                For streaming: should be ResponseStream[ChatResponseUpdate, ChatResponse].
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
        kwargs: Additional keyword arguments passed to the chat client.
        stream_update_hooks: Hooks applied to each streamed update.
        stream_finalizers: Hooks applied to the finalized response.
        stream_teardown_hooks: Hooks executed after stream consumption.

    Examples:
        .. code-block:: python

            from agent_framework import ChatMiddleware, ChatContext


            class TokenCounterMiddleware(ChatMiddleware):
                async def process(self, context: ChatContext, next):
                    print(f"Chat client: {context.chat_client.__class__.__name__}")
                    print(f"Messages: {len(context.messages)}")
                    print(f"Model: {context.options.get('model_id')}")

                    # Store metadata
                    context.metadata["input_tokens"] = self.count_tokens(context.messages)

                    # Continue execution
                    await next(context)

                    # Access result and count output tokens
                    if context.result:
                        context.metadata["output_tokens"] = self.count_tokens(context.result)
    """

    INJECTABLE: ClassVar[set[str]] = {"chat_client", "result"}

    def __init__(
        self,
        chat_client: "ChatClientProtocol",
        messages: "MutableSequence[ChatMessage]",
        options: Mapping[str, Any] | None,
        is_streaming: bool = False,
        metadata: dict[str, Any] | None = None,
        result: "ChatResponse | ResponseStream[ChatResponseUpdate, ChatResponse] | None" = None,
        terminate: bool = False,
        kwargs: dict[str, Any] | None = None,
        stream_update_hooks: Sequence[
            Callable[[ChatResponseUpdate], ChatResponseUpdate | Awaitable[ChatResponseUpdate]]
        ]
        | None = None,
        stream_finalizers: Sequence[Callable[[ChatResponse], ChatResponse | Awaitable[ChatResponse]]] | None = None,
        stream_teardown_hooks: Sequence[Callable[[], Awaitable[None] | None]] | None = None,
    ) -> None:
        """Initialize the ChatContext.

        Args:
            chat_client: The chat client being invoked.
            messages: The messages being sent to the chat client.
            options: The options for the chat request as a dict.
            is_streaming: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between chat middleware.
            result: Chat execution result.
            terminate: A flag indicating whether to terminate execution after current middleware.
            kwargs: Additional keyword arguments passed to the chat client.
            stream_update_hooks: Update hooks to apply to a streaming response.
            stream_finalizers: Finalizers to apply to the finalized streaming response.
            stream_teardown_hooks: Teardown hooks to run after streaming completes.
        """
        self.chat_client = chat_client
        self.messages = messages
        self.options = options
        self.is_streaming = is_streaming
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.terminate = terminate
        self.kwargs = kwargs if kwargs is not None else {}
        self.stream_update_hooks = list(stream_update_hooks or [])
        self.stream_finalizers = list(stream_finalizers or [])
        self.stream_teardown_hooks = list(stream_teardown_hooks or [])


class AgentMiddleware(ABC):
    """Abstract base class for agent middleware that can intercept agent invocations.

    Agent middleware allows you to intercept and modify agent invocations before and after
    execution. You can inspect messages, modify context, override results, or terminate
    execution early.

    Note:
        AgentMiddleware is an abstract base class. You must subclass it and implement
        the ``process()`` method to create custom agent middleware.

    Examples:
        .. code-block:: python

            from agent_framework import AgentMiddleware, AgentRunContext, ChatAgent


            class RetryMiddleware(AgentMiddleware):
                def __init__(self, max_retries: int = 3):
                    self.max_retries = max_retries

                async def process(self, context: AgentRunContext, next):
                    for attempt in range(self.max_retries):
                        await next(context)
                        if context.result and not context.result.is_error:
                            break
                        print(f"Retry {attempt + 1}/{self.max_retries}")


            # Use with an agent
            agent = ChatAgent(chat_client=client, name="assistant", middleware=[RetryMiddleware()])
    """

    @abstractmethod
    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
    ) -> None:
        """Process an agent invocation.

        Args:
            context: Agent invocation context containing agent, messages, and metadata.
                    Use context.is_streaming to determine if this is a streaming call.
                    Middleware can set context.result to override execution, or observe
                    the actual execution result after calling next().
                    For non-streaming: AgentResponse
                    For streaming: AsyncIterable[AgentResponseUpdate]
            next: Function to call the next middleware or final agent execution.
                  Does not return anything - all data flows through the context.

        Note:
            Middleware should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling next() for actual results.
        """
        ...


class FunctionMiddleware(ABC):
    """Abstract base class for function middleware that can intercept function invocations.

    Function middleware allows you to intercept and modify function/tool invocations before
    and after execution. You can validate arguments, cache results, log invocations, or
    override function execution.

    Note:
        FunctionMiddleware is an abstract base class. You must subclass it and implement
        the ``process()`` method to create custom function middleware.

    Examples:
        .. code-block:: python

            from agent_framework import FunctionMiddleware, FunctionInvocationContext, ChatAgent


            class CachingMiddleware(FunctionMiddleware):
                def __init__(self):
                    self.cache = {}

                async def process(self, context: FunctionInvocationContext, next):
                    cache_key = f"{context.function.name}:{context.arguments}"

                    # Check cache
                    if cache_key in self.cache:
                        context.result = self.cache[cache_key]
                        context.terminate = True
                        return

                    # Execute function
                    await next(context)

                    # Cache result
                    if context.result:
                        self.cache[cache_key] = context.result


            # Use with an agent
            agent = ChatAgent(chat_client=client, name="assistant", middleware=[CachingMiddleware()])
    """

    @abstractmethod
    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Process a function invocation.

        Args:
            context: Function invocation context containing function, arguments, and metadata.
                    Middleware can set context.result to override execution, or observe
                    the actual execution result after calling next().
            next: Function to call the next middleware or final function execution.
                  Does not return anything - all data flows through the context.

        Note:
            Middleware should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling next() for actual results.
        """
        ...


class ChatMiddleware(ABC):
    """Abstract base class for chat middleware that can intercept chat client requests.

    Chat middleware allows you to intercept and modify chat client requests before and after
    execution. You can modify messages, add system prompts, log requests, or override
    chat responses.

    Note:
        ChatMiddleware is an abstract base class. You must subclass it and implement
        the ``process()`` method to create custom chat middleware.

    Examples:
        .. code-block:: python

            from agent_framework import ChatMiddleware, ChatContext, ChatAgent


            class SystemPromptMiddleware(ChatMiddleware):
                def __init__(self, system_prompt: str):
                    self.system_prompt = system_prompt

                async def process(self, context: ChatContext, next):
                    # Add system prompt to messages
                    from agent_framework import ChatMessage

                    context.messages.insert(0, ChatMessage("system", [self.system_prompt]))

                    # Continue execution
                    await next(context)


            # Use with an agent
            agent = ChatAgent(
                chat_client=client,
                name="assistant",
                middleware=[SystemPromptMiddleware("You are a helpful assistant.")],
            )
    """

    @abstractmethod
    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:
        """Process a chat client request.

        Args:
            context: Chat invocation context containing chat client, messages, options, and metadata.
                    Use context.is_streaming to determine if this is a streaming call.
                    Middleware can set context.result to override execution, or observe
                    the actual execution result after calling next().
                    For non-streaming: ChatResponse
                    For streaming: ResponseStream[ChatResponseUpdate, ChatResponse]
            next: Function to call the next middleware or final chat execution.
                  Does not return anything - all data flows through the context.

        Note:
            Middleware should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling next() for actual results.
        """
        ...


# Pure function type definitions for convenience
AgentMiddlewareCallable = Callable[[AgentRunContext, Callable[[AgentRunContext], Awaitable[None]]], Awaitable[None]]

FunctionMiddlewareCallable = Callable[
    [FunctionInvocationContext, Callable[[FunctionInvocationContext], Awaitable[None]]], Awaitable[None]
]

ChatMiddlewareCallable = Callable[[ChatContext, Callable[[ChatContext], Awaitable[None]]], Awaitable[None]]

# Type alias for all middleware types
Middleware: TypeAlias = (
    AgentMiddleware
    | AgentMiddlewareCallable
    | FunctionMiddleware
    | FunctionMiddlewareCallable
    | ChatMiddleware
    | ChatMiddlewareCallable
)
AgentMiddlewareTypes: TypeAlias = AgentMiddleware | AgentMiddlewareCallable

# region Middleware type markers for decorators


def agent_middleware(func: AgentMiddlewareCallable) -> AgentMiddlewareCallable:
    """Decorator to mark a function as agent middleware.

    This decorator explicitly identifies a function as agent middleware,
    which processes AgentRunContext objects.

    Args:
        func: The middleware function to mark as agent middleware.

    Returns:
        The same function with agent middleware marker.

    Examples:
        .. code-block:: python

            from agent_framework import agent_middleware, AgentRunContext, ChatAgent


            @agent_middleware
            async def logging_middleware(context: AgentRunContext, next):
                print(f"Before: {context.agent.name}")
                await next(context)
                print(f"After: {context.result}")


            # Use with an agent
            agent = ChatAgent(chat_client=client, name="assistant", middleware=[logging_middleware])
    """
    # Add marker attribute to identify this as agent middleware
    func._middleware_type: MiddlewareType = MiddlewareType.AGENT  # type: ignore
    return func


def function_middleware(func: FunctionMiddlewareCallable) -> FunctionMiddlewareCallable:
    """Decorator to mark a function as function middleware.

    This decorator explicitly identifies a function as function middleware,
    which processes FunctionInvocationContext objects.

    Args:
        func: The middleware function to mark as function middleware.

    Returns:
        The same function with function middleware marker.

    Examples:
        .. code-block:: python

            from agent_framework import function_middleware, FunctionInvocationContext, ChatAgent


            @function_middleware
            async def logging_middleware(context: FunctionInvocationContext, next):
                print(f"Calling: {context.function.name}")
                await next(context)
                print(f"Result: {context.result}")


            # Use with an agent
            agent = ChatAgent(chat_client=client, name="assistant", middleware=[logging_middleware])
    """
    # Add marker attribute to identify this as function middleware
    func._middleware_type: MiddlewareType = MiddlewareType.FUNCTION  # type: ignore
    return func


def chat_middleware(func: ChatMiddlewareCallable) -> ChatMiddlewareCallable:
    """Decorator to mark a function as chat middleware.

    This decorator explicitly identifies a function as chat middleware,
    which processes ChatContext objects.

    Args:
        func: The middleware function to mark as chat middleware.

    Returns:
        The same function with chat middleware marker.

    Examples:
        .. code-block:: python

            from agent_framework import chat_middleware, ChatContext, ChatAgent


            @chat_middleware
            async def logging_middleware(context: ChatContext, next):
                print(f"Messages: {len(context.messages)}")
                await next(context)
                print(f"Response: {context.result}")


            # Use with an agent
            agent = ChatAgent(chat_client=client, name="assistant", middleware=[logging_middleware])
    """
    # Add marker attribute to identify this as chat middleware
    func._middleware_type: MiddlewareType = MiddlewareType.CHAT  # type: ignore
    return func


class MiddlewareWrapper(Generic[TContext]):
    """Generic wrapper to convert pure functions into middleware protocol objects.

    This wrapper allows function-based middleware to be used alongside class-based middleware
    by providing a unified interface.

    Type Parameters:
        TContext: The type of context object this middleware operates on.
    """

    def __init__(self, func: Callable[[TContext, Callable[[TContext], Awaitable[None]]], Awaitable[None]]) -> None:
        self.func = func

    async def process(self, context: TContext, next: Callable[[TContext], Awaitable[None]]) -> None:
        await self.func(context, next)


class BaseMiddlewarePipeline(ABC):
    """Base class for middleware pipeline execution.

    Provides common functionality for building and executing middleware chains.
    """

    def __init__(self) -> None:
        """Initialize the base middleware pipeline."""
        self._middleware: list[Any] = []

    @abstractmethod
    def _register_middleware(self, middleware: Any) -> None:
        """Register a middleware item.

        Must be implemented by subclasses.

        Args:
            middleware: The middleware to register.
        """
        ...

    @property
    def has_middlewares(self) -> bool:
        """Check if there are any middleware registered.

        Returns:
            True if middleware are registered, False otherwise.
        """
        return bool(self._middleware)

    def _register_middleware_with_wrapper(
        self,
        middleware: Any,
        expected_type: type,
    ) -> None:
        """Generic middleware registration with automatic wrapping.

        Wraps callable middleware in a MiddlewareWrapper if needed.

        Args:
            middleware: The middleware instance or callable to register.
            expected_type: The expected middleware base class type.
        """
        if isinstance(middleware, expected_type):
            self._middleware.append(middleware)
        elif callable(middleware):
            self._middleware.append(MiddlewareWrapper(middleware))  # type: ignore[arg-type]

    def _create_handler_chain(
        self,
        final_handler: Callable[[Any], Awaitable[Any]],
        result_container: dict[str, Any],
        result_key: str = "result",
    ) -> Callable[[Any], Awaitable[None]]:
        """Create a chain of middleware handlers.

        Args:
            final_handler: The final handler to execute.
            result_container: Container to store the result.
            result_key: Key to use in the result container.

        Returns:
            The first handler in the chain.
        """

        def create_next_handler(index: int) -> Callable[[Any], Awaitable[None]]:
            if index >= len(self._middleware):

                async def final_wrapper(c: Any) -> None:
                    # Execute actual handler and populate context for observability
                    result = await final_handler(c)
                    result_container[result_key] = result
                    c.result = result

                return final_wrapper

            middleware = self._middleware[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: Any) -> None:
                await middleware.process(c, next_handler)

            return current_handler

        return create_next_handler(0)

    def _create_streaming_handler_chain(
        self,
        final_handler: Callable[[Any], Any],
        result_container: dict[str, Any],
        result_key: str = "result_stream",
    ) -> Callable[[Any], Awaitable[None]]:
        """Create a chain of middleware handlers for streaming operations.

        Args:
            final_handler: The final handler to execute.
            result_container: Container to store the result.
            result_key: Key to use in the result container.

        Returns:
            The first handler in the chain.
        """

        def create_next_handler(index: int) -> Callable[[Any], Awaitable[None]]:
            if index >= len(self._middleware):

                async def final_wrapper(c: Any) -> None:
                    # If terminate was set, skip execution
                    if c.terminate:
                        return

                    # Execute actual handler and populate context for observability
                    # Note: final_handler might not be awaitable for streaming cases
                    try:
                        result = await final_handler(c)
                    except TypeError:
                        # Handle non-awaitable case (e.g., generator functions)
                        result = final_handler(c)
                    result_container[result_key] = result
                    c.result = result

                return final_wrapper

            middleware = self._middleware[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: Any) -> None:
                await middleware.process(c, next_handler)
                # If terminate is set, don't continue the pipeline
                if c.terminate:
                    return

            return current_handler

        return create_next_handler(0)


class AgentMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes agent middleware in a chain.

    Manages the execution of multiple agent middleware in sequence, allowing each middleware
    to process the agent invocation and pass control to the next middleware in the chain.
    """

    def __init__(self, middleware: Sequence[AgentMiddlewareTypes] | None = None):
        """Initialize the agent middleware pipeline.

        Args:
            middleware: The list of agent middleware to include in the pipeline.
        """
        super().__init__()
        self._middleware: list[AgentMiddleware] = []

        if middleware:
            for mdlware in middleware:
                self._register_middleware(mdlware)

    def _register_middleware(self, middleware: AgentMiddlewareTypes) -> None:
        """Register an agent middleware item.

        Args:
            middleware: The agent middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, AgentMiddleware)

    async def execute(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        context: AgentRunContext,
        final_handler: Callable[[AgentRunContext], Awaitable[AgentResponse]],
    ) -> AgentResponse | None:
        """Execute the agent middleware pipeline for non-streaming.

        Args:
            agent: The agent being invoked.
            messages: The messages to send to the agent.
            context: The agent invocation context.
            final_handler: The final handler that performs the actual agent execution.

        Returns:
            The agent response after processing through all middleware.
        """
        # Update context with agent and messages
        context.agent = agent
        context.messages = messages
        context.is_streaming = False

        if not self._middleware:
            return await final_handler(context)

        # Store the final result
        result_container: dict[str, AgentResponse | None] = {"result": None}

        # Custom final handler that handles termination and result override
        async def agent_final_handler(c: AgentRunContext) -> AgentResponse:
            # If terminate was set, return the result (which might be None)
            if c.terminate:
                if c.result is not None and isinstance(c.result, AgentResponse):
                    return c.result
                return AgentResponse()
            # Execute actual handler and populate context for observability
            return await final_handler(c)

        first_handler = self._create_handler_chain(agent_final_handler, result_container, "result")
        await first_handler(context)

        # Return the result from result container or overridden result
        if context.result is not None and isinstance(context.result, AgentResponse):
            return context.result

        # If no result was set (next() not called), return empty AgentResponse
        response = result_container.get("result")
        if response is None:
            return AgentResponse()
        return response

    async def execute_stream(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        context: AgentRunContext,
        final_handler: Callable[[AgentRunContext], ResponseStream[AgentResponseUpdate, AgentResponse]],
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Execute the agent middleware pipeline for streaming.

        Args:
            agent: The agent being invoked.
            messages: The messages to send to the agent.
            context: The agent invocation context.
            final_handler: The final handler that performs the actual agent streaming execution.

        Returns:
            ResponseStream of agent response updates.
        """
        # Update context with agent and messages
        context.agent = agent
        context.messages = messages
        context.is_streaming = True

        if not self._middleware:
            result = final_handler(context)
            if isinstance(result, Awaitable):
                result = await result
            if not isinstance(result, ResponseStream):
                raise ValueError("Streaming agent middleware requires a ResponseStream result.")
            return result

        # Store the final result
        result_container: dict[str, ResponseStream[AgentResponseUpdate, AgentResponse] | None] = {"result_stream": None}

        first_handler = self._create_streaming_handler_chain(final_handler, result_container, "result_stream")
        await first_handler(context)

        stream = context.result if isinstance(context.result, ResponseStream) else result_container["result_stream"]
        if not isinstance(stream, ResponseStream):
            if context.terminate or result_container["result_stream"] is None:

                async def _empty() -> AsyncIterable[AgentResponseUpdate]:
                    await asyncio.sleep(0)
                    if False:
                        yield AgentResponseUpdate()

                return ResponseStream(_empty())
            raise ValueError("Streaming agent middleware requires a ResponseStream result.")
        return stream


class FunctionMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes function middleware in a chain.

    Manages the execution of multiple function middleware in sequence, allowing each middleware
    to process the function invocation and pass control to the next middleware in the chain.
    """

    def __init__(self, *middleware: FunctionMiddleware | FunctionMiddlewareCallable):
        """Initialize the function middleware pipeline.

        Args:
            middleware: The list of function middleware to include in the pipeline.
        """
        super().__init__()
        self._middleware: list[FunctionMiddleware] = []

        if middleware:
            for mdlware in middleware:
                self._register_middleware(mdlware)

    def _register_middleware(self, middleware: FunctionMiddleware | FunctionMiddlewareCallable) -> None:
        """Register a function middleware item.

        Args:
            middleware: The function middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, FunctionMiddleware)

    async def execute(
        self,
        function: Any,
        arguments: "BaseModel",
        context: FunctionInvocationContext,
        final_handler: Callable[[FunctionInvocationContext], Awaitable[Any]],
    ) -> Any:
        """Execute the function middleware pipeline.

        Args:
            function: The function being invoked.
            arguments: The validated arguments for the function.
            context: The function invocation context.
            final_handler: The final handler that performs the actual function execution.

        Returns:
            The function result after processing through all middleware.
        """
        # Update context with function and arguments
        context.function = function
        context.arguments = arguments

        if not self._middleware:
            return await final_handler(context)

        # Store the final result
        result_container: dict[str, Any] = {"result": None}

        # Custom final handler that handles pre-existing results
        async def function_final_handler(c: FunctionInvocationContext) -> Any:
            # If terminate was set, skip execution and return the result (which might be None)
            if c.terminate:
                return c.result
            # Execute actual handler and populate context for observability
            return await final_handler(c)

        first_handler = self._create_handler_chain(function_final_handler, result_container, "result")
        await first_handler(context)

        # Return the result from result container or overridden result
        if context.result is not None:
            return context.result
        return result_container["result"]


class ChatMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes chat middleware in a chain.

    Manages the execution of multiple chat middleware in sequence, allowing each middleware
    to process the chat request and pass control to the next middleware in the chain.
    """

    def __init__(self, *middleware: ChatMiddleware | ChatMiddlewareCallable):
        """Initialize the chat middleware pipeline.

        Args:
            middleware: The list of chat middleware to include in the pipeline.
        """
        super().__init__()
        self._middleware: list[ChatMiddleware] = []

        if middleware:
            for mdlware in middleware:
                self._register_middleware(mdlware)

    def _register_middleware(self, middleware: ChatMiddleware | ChatMiddlewareCallable) -> None:
        """Register a chat middleware item.

        Args:
            middleware: The chat middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, ChatMiddleware)

    async def execute(
        self,
        context: ChatContext,
        final_handler: Callable[
            [ChatContext], Awaitable["ChatResponse"] | ResponseStream["ChatResponseUpdate", "ChatResponse"]
        ],
        **kwargs: Any,
    ) -> Awaitable["ChatResponse"] | ResponseStream["ChatResponseUpdate", "ChatResponse"]:
        """Execute the chat middleware pipeline.

        Args:
            context: The chat invocation context.
            final_handler: The final handler that performs the actual chat execution.
            **kwargs: Additional keyword arguments.

        Returns:
            The chat response after processing through all middleware.
        """
        if not self._middleware:
            if context.is_streaming:
                return final_handler(context)
            return await final_handler(context)  # type: ignore[return-value]

        if context.is_streaming:
            result_container: dict[str, Any] = {"result_stream": None}

            def stream_final_handler(ctx: ChatContext) -> ResponseStream["ChatResponseUpdate", "ChatResponse"]:
                if ctx.terminate:
                    return ctx.result  # type: ignore[return-value]
                return final_handler(ctx)  # type: ignore[return-value]

            first_handler = self._create_streaming_handler_chain(
                stream_final_handler, result_container, "result_stream"
            )
            await first_handler(context)

            stream = context.result if isinstance(context.result, ResponseStream) else result_container["result_stream"]
            if not isinstance(stream, ResponseStream):
                raise ValueError("Streaming chat middleware requires a ResponseStream result.")

            for hook in context.stream_update_hooks:
                stream.with_update_hook(hook)
            for finalizer in context.stream_finalizers:
                stream.with_finalizer(finalizer)
            for teardown_hook in context.stream_teardown_hooks:
                stream.with_teardown(teardown_hook)  # type: ignore[arg-type]
            return stream

        async def _run() -> "ChatResponse":
            result_container: dict[str, Any] = {"result": None}

            async def chat_final_handler(c: ChatContext) -> "ChatResponse":
                if c.terminate:
                    return c.result  # type: ignore
                return await final_handler(c)  # type: ignore[return-value]

            first_handler = self._create_handler_chain(chat_final_handler, result_container, "result")
            await first_handler(context)

            if context.result is not None:
                return context.result  # type: ignore
            return result_container["result"]  # type: ignore

        return await _run()  # type: ignore[return-value]


# Covariant for chat client options
TOptions_co = TypeVar(
    "TOptions_co",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class ChatMiddlewareMixin(Generic[TOptions_co]):
    """Mixin for chat clients to apply chat middleware around response generation."""

    def __init__(
        self,
        *,
        middleware: (
            Sequence[ChatMiddleware | ChatMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable] | None
        ) = None,
        **kwargs: Any,
    ) -> None:
        middleware_list = categorize_middleware(middleware)
        self.chat_middleware = middleware_list["chat"]
        self.function_middleware = middleware_list["function"]
        super().__init__(**kwargs)

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "ChatOptions[TResponseModelT]",
        **kwargs: Any,
    ) -> "Awaitable[ChatResponse[TResponseModelT]]": ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[False] = ...,
        options: "TOptions_co | ChatOptions[None] | None" = None,
        **kwargs: Any,
    ) -> "Awaitable[ChatResponse[Any]]": ...

    @overload
    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: Literal[True],
        options: "TOptions_co | ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]": ...

    def get_response(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage],
        *,
        stream: bool = False,
        options: "TOptions_co | ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> "Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]":
        """Execute the chat pipeline if middleware is configured."""
        call_middleware = kwargs.pop("middleware", [])
        middleware = categorize_middleware(call_middleware)
        chat_middleware_list = middleware["chat"]  # type: ignore[assignment]
        function_middleware_list = middleware["function"]

        if function_middleware_list or self.function_middleware:
            kwargs["_function_middleware_pipeline"] = FunctionMiddlewarePipeline(
                *function_middleware_list, *self.function_middleware
            )

        if not chat_middleware_list and not self.chat_middleware:
            return super().get_response(  # type: ignore[misc,no-any-return]
                messages=messages,
                stream=stream,
                options=options,
                **kwargs,
            )

        pipeline = ChatMiddlewarePipeline(*chat_middleware_list, *self.chat_middleware)  # type: ignore[arg-type]
        prepared_messages = prepare_messages(messages)
        context = ChatContext(
            chat_client=self,  # type: ignore[arg-type]
            messages=prepared_messages,
            options=options,
            is_streaming=stream,
            kwargs=kwargs,
        )

        def final_handler(
            ctx: ChatContext,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            return super(ChatMiddlewareMixin, self).get_response(  # type: ignore[misc,no-any-return]
                messages=list(ctx.messages),
                stream=ctx.is_streaming,
                options=ctx.options or {},
                **ctx.kwargs,
            )

        result = pipeline.execute(
            chat_client=self,  # type: ignore[arg-type]
            messages=context.messages,
            options=options,
            context=context,
            final_handler=final_handler,
            **kwargs,
        )

        if stream:
            return ResponseStream.wrap(result)  # type: ignore[arg-type,return-value]
        return result  # type: ignore[return-value]


class AgentMiddlewareMixin:
    """Mixin for agents to apply agent middleware around run execution."""

    @overload
    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: Literal[False] = ...,
        thread: "AgentThread | None" = None,
        middleware: Sequence[Middleware] | None = None,
        options: "ChatOptions[TResponseModelT]",
        **kwargs: Any,
    ) -> "Awaitable[AgentResponse[TResponseModelT]]": ...

    @overload
    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: Literal[False] = ...,
        thread: "AgentThread | None" = None,
        middleware: Sequence[Middleware] | None = None,
        options: "ChatOptions[None] | None" = None,
        **kwargs: Any,
    ) -> "Awaitable[AgentResponse[Any]]": ...

    @overload
    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: Literal[True],
        thread: "AgentThread | None" = None,
        middleware: Sequence[Middleware] | None = None,
        options: "ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]": ...

    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: "AgentThread | None" = None,
        middleware: Sequence[Middleware] | None = None,
        options: "ChatOptions[Any] | None" = None,
        **kwargs: Any,
    ) -> "Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]":
        """Middleware-enabled unified run method."""
        return _middleware_enabled_run_impl(
            self, super().run, messages, stream, thread, middleware, options=options, **kwargs
        )  # type: ignore[misc]


def _determine_middleware_type(middleware: Any) -> MiddlewareType:
    """Determine middleware type using decorator and/or parameter type annotation.

    Args:
        middleware: The middleware function to analyze.

    Returns:
        MiddlewareType.AGENT, MiddlewareType.FUNCTION, or MiddlewareType.CHAT indicating the middleware type.

    Raises:
        MiddlewareException: When middleware type cannot be determined or there's a mismatch.
    """
    # Check for decorator marker
    decorator_type: MiddlewareType | None = getattr(middleware, "_middleware_type", None)

    # Check for parameter type annotation
    param_type: MiddlewareType | None = None
    try:
        sig = inspect.signature(middleware)
        params = list(sig.parameters.values())

        # Must have at least 2 parameters (context and next)
        if len(params) >= 2:
            first_param = params[0]
            if hasattr(first_param.annotation, "__name__"):
                annotation_name = first_param.annotation.__name__
                if annotation_name == "AgentRunContext":
                    param_type = MiddlewareType.AGENT
                elif annotation_name == "FunctionInvocationContext":
                    param_type = MiddlewareType.FUNCTION
                elif annotation_name == "ChatContext":
                    param_type = MiddlewareType.CHAT
        else:
            # Not enough parameters - can't be valid middleware
            raise MiddlewareException(
                f"Middleware function must have at least 2 parameters (context, next), "
                f"but {middleware.__name__} has {len(params)}"
            )
    except Exception as e:
        if isinstance(e, MiddlewareException):
            raise
        # Signature inspection failed - continue with other checks
        pass

    if decorator_type and param_type:
        # Both decorator and parameter type specified - they must match
        if decorator_type != param_type:
            raise MiddlewareException(
                f"Middleware type mismatch: decorator indicates '{decorator_type.value}' "
                f"but parameter type indicates '{param_type.value}' for function {middleware.__name__}"
            )
        return decorator_type

    if decorator_type:
        # Just decorator specified - rely on decorator
        return decorator_type

    if param_type:
        # Just parameter type specified - rely on types
        return param_type

    # Neither decorator nor parameter type specified - throw exception
    raise MiddlewareException(
        f"Cannot determine middleware type for function {middleware.__name__}. "
        f"Please either use @agent_middleware/@function_middleware/@chat_middleware decorators "
        f"or specify parameter types (AgentRunContext, FunctionInvocationContext, or ChatContext)."
    )


# Decorator for adding middleware support to agent classes
def _build_agent_middleware_pipelines(
    agent_level_middlewares: Sequence[Middleware] | None,
    run_level_middlewares: Sequence[Middleware] | None = None,
) -> tuple[AgentMiddlewarePipeline, FunctionMiddlewarePipeline, list[ChatMiddleware | ChatMiddlewareCallable]]:
    """Build fresh agent and function middleware pipelines from the provided middleware lists."""
    middleware = categorize_middleware(*(agent_level_middlewares or ()), *(run_level_middlewares or ()))

    return (
        AgentMiddlewarePipeline(middleware["agent"]),  # type: ignore[arg-type]
        FunctionMiddlewarePipeline(*middleware["function"]),  # type: ignore[arg-type]
        middleware["chat"],  # type: ignore[return-value]
    )


def use_agent_middleware(agent_class: type[TAgent]) -> type[TAgent]:
    """Class decorator that adds middleware support to an agent class.

    This decorator adds middleware functionality to any agent class.
    It wraps the unified ``run()`` method to provide middleware execution for both
    streaming and non-streaming calls.

    The middleware execution can be terminated at any point by setting the
    ``context.terminate`` property to True. Once set, the pipeline will stop executing
    further middleware as soon as control returns to the pipeline.

    Note:
        This decorator is already applied to built-in agent classes. You only need to use
        it if you're creating custom agent implementations.

    Args:
        agent_class: The agent class to add middleware support to.

    Returns:
        The modified agent class with middleware support.

    Examples:
        .. code-block:: python

            from agent_framework import use_agent_middleware


            @use_agent_middleware
            class CustomAgent:
                async def run(self, messages, *, stream=False, **kwargs):
                    # Agent implementation
                    pass
    """
    # Store original method
    original_run = agent_class.run  # type: ignore[attr-defined]

    def middleware_enabled_run(
        self: Any,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: Any = None,
        middleware: Sequence[Middleware] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | AsyncIterable[AgentResponseUpdate]:
        """Middleware-enabled unified run method."""
        return _middleware_enabled_run_impl(self, original_run, messages, stream, thread, middleware, **kwargs)

    agent_class.run = update_wrapper(middleware_enabled_run, original_run)  # type: ignore

    return agent_class


def _middleware_enabled_run_impl(
    self: Any,
    original_run: Any,
    messages: str | ChatMessage | Sequence[str | ChatMessage] | None,
    stream: bool,
    thread: Any,
    middleware: Sequence[Middleware] | None,
    **kwargs: Any,
) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
    """Internal implementation for middleware-enabled run (both streaming and non-streaming)."""

    def _call_original(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if getattr(original_run, "__self__", None) is not None:
            return original_run(*args, **kwargs)
        return original_run(self, *args, **kwargs)

    # Build fresh middleware pipelines from current middleware collection and run-level middleware
    agent_middleware = getattr(self, "middleware", None)
    agent_pipeline, function_pipeline, chat_middlewares = _build_agent_middleware_pipelines(
        agent_middleware, middleware
    )

    # Add function middleware pipeline to kwargs if available
    if function_pipeline.has_middlewares:
        kwargs["_function_middleware_pipeline"] = function_pipeline

    # Pass chat middleware through kwargs for run-level application
    if chat_middlewares:
        kwargs["middleware"] = chat_middlewares

    normalized_messages = prepare_messages(messages)

    # Execute with middleware if available
    if agent_pipeline.has_middlewares:
        context = AgentRunContext(
            agent=self,  # type: ignore[arg-type]
            messages=normalized_messages,
            thread=thread,
            is_streaming=stream,
            kwargs=kwargs,
        )

        if stream:

            async def _execute_stream_handler(
                ctx: AgentRunContext,
            ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
                result = _call_original(ctx.messages, stream=True, thread=thread, **ctx.kwargs)
                if isinstance(result, Awaitable):
                    result = await result
                if not isinstance(result, ResponseStream):
                    raise MiddlewareException("Streaming agent middleware requires a ResponseStream result.")
                return result

            return ResponseStream.wrap(
                agent_pipeline.execute_stream(
                    self,  # type: ignore[arg-type]
                    normalized_messages,
                    context,
                    _execute_stream_handler,  # type: ignore[arg-type]
                )
            )

        async def _execute_handler(ctx: AgentRunContext) -> AgentResponse:
            return await _call_original(ctx.messages, stream=False, thread=thread, **ctx.kwargs)  # type: ignore

        async def _wrapper() -> AgentResponse:
            result = await agent_pipeline.execute(
                self,  # type: ignore[arg-type]
                normalized_messages,
                context,
                _execute_handler,
            )
            return result if result else AgentResponse()

        return _wrapper()

    # No middleware, execute directly
    if stream:
        return _call_original(normalized_messages, stream=True, thread=thread, **kwargs)  # type: ignore[no-any-return]
    return _call_original(normalized_messages, stream=False, thread=thread, **kwargs)  # type: ignore[no-any-return]


class MiddlewareDict(TypedDict):
    agent: list[AgentMiddleware | AgentMiddlewareCallable]
    function: list[FunctionMiddleware | FunctionMiddlewareCallable]
    chat: list[ChatMiddleware | ChatMiddlewareCallable]


def categorize_middleware(
    *middleware_sources: Middleware | Sequence[Middleware] | None,
) -> MiddlewareDict:
    """Categorize middleware from multiple sources into agent, function, and chat types.

    Args:
        *middleware_sources: Variable number of middleware sources to categorize.

    Returns:
        Dict with keys "agent", "function", "chat" containing lists of categorized middleware.
    """
    result: MiddlewareDict = {"agent": [], "function": [], "chat": []}

    # Merge all middleware sources into a single list
    all_middleware: list[Any] = []
    for source in middleware_sources:
        if source:
            if isinstance(source, list):
                all_middleware.extend(source)  # type: ignore
            else:
                all_middleware.append(source)

    # Categorize each middleware item
    for middleware in all_middleware:
        if isinstance(middleware, AgentMiddleware):
            result["agent"].append(middleware)
        elif isinstance(middleware, FunctionMiddleware):
            result["function"].append(middleware)
        elif isinstance(middleware, ChatMiddleware):
            result["chat"].append(middleware)
        elif callable(middleware):
            # Always call _determine_middleware_type to ensure proper validation
            middleware_type = _determine_middleware_type(middleware)
            if middleware_type == MiddlewareType.AGENT:
                result["agent"].append(middleware)  # type: ignore
            elif middleware_type == MiddlewareType.FUNCTION:
                result["function"].append(middleware)  # type: ignore
            elif middleware_type == MiddlewareType.CHAT:
                result["chat"].append(middleware)  # type: ignore
        else:
            # Fallback to agent middleware for unknown types
            result["agent"].append(middleware)

    return result


def create_function_middleware_pipeline(
    *middleware_sources: Middleware,
) -> FunctionMiddlewarePipeline | None:
    """Create a function middleware pipeline from multiple middleware sources.

    Args:
        *middleware_sources: Variable number of middleware sources.

    Returns:
        A FunctionMiddlewarePipeline if function middleware is found, None otherwise.
    """
    function_middlewares = categorize_middleware(*middleware_sources)["function"]
    return FunctionMiddlewarePipeline(function_middlewares) if function_middlewares else None  # type: ignore[arg-type]
