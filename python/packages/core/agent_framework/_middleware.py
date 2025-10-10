# Copyright (c) Microsoft. All rights reserved.

import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, MutableSequence
from enum import Enum
from functools import update_wrapper
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias, TypeVar

from ._serialization import SerializationMixin
from ._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage
from .exceptions import MiddlewareException

if TYPE_CHECKING:
    from pydantic import BaseModel

    from ._agents import AgentProtocol
    from ._clients import ChatClientProtocol
    from ._tools import AIFunction
    from ._types import ChatOptions, ChatResponse, ChatResponseUpdate


__all__ = [
    "AgentMiddleware",
    "AgentMiddlewares",
    "AgentRunContext",
    "ChatContext",
    "ChatMiddleware",
    "FunctionInvocationContext",
    "FunctionMiddleware",
    "Middleware",
    "agent_middleware",
    "chat_middleware",
    "function_middleware",
    "use_agent_middleware",
    "use_chat_middleware",
]

TAgent = TypeVar("TAgent", bound="AgentProtocol")
TChatClient = TypeVar("TChatClient", bound="ChatClientProtocol")
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
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between agent middleware.
        result: Agent execution result. Can be observed after calling ``next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be AgentRunResponse.
                For streaming: should be AsyncIterable[AgentRunResponseUpdate].
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
                    print(f"Streaming: {context.is_streaming}")

                    # Store metadata
                    context.metadata["start_time"] = time.time()

                    # Continue execution
                    await next(context)

                    # Access result after execution
                    print(f"Result: {context.result}")
    """

    INJECTABLE: ClassVar[set[str]] = {"agent", "result"}

    def __init__(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        is_streaming: bool = False,
        metadata: dict[str, Any] | None = None,
        result: AgentRunResponse | AsyncIterable[AgentRunResponseUpdate] | None = None,
        terminate: bool = False,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the AgentRunContext.

        Args:
            agent: The agent being invoked.
            messages: The messages being sent to the agent.
            is_streaming: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between agent middleware.
            result: Agent execution result.
            terminate: A flag indicating whether to terminate execution after current middleware.
            kwargs: Additional keyword arguments passed to the agent run method.
        """
        self.agent = agent
        self.messages = messages
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
        function: "AIFunction[Any, Any]",
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
        chat_options: The options for the chat request.
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between chat middleware.
        result: Chat execution result. Can be observed after calling ``next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be ChatResponse.
                For streaming: should be AsyncIterable[ChatResponseUpdate].
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
        kwargs: Additional keyword arguments passed to the chat client.

    Examples:
        .. code-block:: python

            from agent_framework import ChatMiddleware, ChatContext


            class TokenCounterMiddleware(ChatMiddleware):
                async def process(self, context: ChatContext, next):
                    print(f"Chat client: {context.chat_client.__class__.__name__}")
                    print(f"Messages: {len(context.messages)}")
                    print(f"Model: {context.chat_options.model_id}")

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
        chat_options: "ChatOptions",
        is_streaming: bool = False,
        metadata: dict[str, Any] | None = None,
        result: "ChatResponse | AsyncIterable[ChatResponseUpdate] | None" = None,
        terminate: bool = False,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the ChatContext.

        Args:
            chat_client: The chat client being invoked.
            messages: The messages being sent to the chat client.
            chat_options: The options for the chat request.
            is_streaming: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between chat middleware.
            result: Chat execution result.
            terminate: A flag indicating whether to terminate execution after current middleware.
            kwargs: Additional keyword arguments passed to the chat client.
        """
        self.chat_client = chat_client
        self.messages = messages
        self.chat_options = chat_options
        self.is_streaming = is_streaming
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.terminate = terminate
        self.kwargs = kwargs if kwargs is not None else {}


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
            agent = ChatAgent(chat_client=client, name="assistant", middleware=RetryMiddleware())
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
                    For non-streaming: AgentRunResponse
                    For streaming: AsyncIterable[AgentRunResponseUpdate]
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
            agent = ChatAgent(chat_client=client, name="assistant", middleware=CachingMiddleware())
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

                    context.messages.insert(0, ChatMessage(role="system", content=self.system_prompt))

                    # Continue execution
                    await next(context)


            # Use with an agent
            agent = ChatAgent(
                chat_client=client, name="assistant", middleware=SystemPromptMiddleware("You are a helpful assistant.")
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
                    For streaming: AsyncIterable[ChatResponseUpdate]
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
AgentMiddlewares: TypeAlias = AgentMiddleware | AgentMiddlewareCallable

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
            agent = ChatAgent(chat_client=client, name="assistant", middleware=logging_middleware)
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
            agent = ChatAgent(chat_client=client, name="assistant", middleware=logging_middleware)
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
            agent = ChatAgent(chat_client=client, name="assistant", middleware=logging_middleware)
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
        self._middlewares: list[Any] = []

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
        """Check if there are any middlewares registered.

        Returns:
            True if middlewares are registered, False otherwise.
        """
        return bool(self._middlewares)

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
            self._middlewares.append(middleware)
        elif callable(middleware):
            self._middlewares.append(MiddlewareWrapper(middleware))  # type: ignore[arg-type]

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
            if index >= len(self._middlewares):

                async def final_wrapper(c: Any) -> None:
                    # Execute actual handler and populate context for observability
                    result = await final_handler(c)
                    result_container[result_key] = result
                    c.result = result

                return final_wrapper

            middleware = self._middlewares[index]
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
            if index >= len(self._middlewares):

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

            middleware = self._middlewares[index]
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

    def __init__(self, middlewares: list[AgentMiddleware | AgentMiddlewareCallable] | None = None):
        """Initialize the agent middleware pipeline.

        Args:
            middlewares: The list of agent middleware to include in the pipeline.
        """
        super().__init__()
        self._middlewares: list[AgentMiddleware] = []

        if middlewares:
            for middleware in middlewares:
                self._register_middleware(middleware)

    def _register_middleware(self, middleware: AgentMiddleware | AgentMiddlewareCallable) -> None:
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
        final_handler: Callable[[AgentRunContext], Awaitable[AgentRunResponse]],
    ) -> AgentRunResponse | None:
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

        if not self._middlewares:
            return await final_handler(context)

        # Store the final result
        result_container: dict[str, AgentRunResponse | None] = {"result": None}

        # Custom final handler that handles termination and result override
        async def agent_final_handler(c: AgentRunContext) -> AgentRunResponse:
            # If terminate was set, return the result (which might be None)
            if c.terminate:
                if c.result is not None and isinstance(c.result, AgentRunResponse):
                    return c.result
                return AgentRunResponse()
            # Execute actual handler and populate context for observability
            return await final_handler(c)

        first_handler = self._create_handler_chain(agent_final_handler, result_container, "result")
        await first_handler(context)

        # Return the result from result container or overridden result
        if context.result is not None and isinstance(context.result, AgentRunResponse):
            return context.result

        # If no result was set (next() not called), return empty AgentRunResponse
        response = result_container.get("result")
        if response is None:
            return AgentRunResponse()
        return response

    async def execute_stream(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        context: AgentRunContext,
        final_handler: Callable[[AgentRunContext], AsyncIterable[AgentRunResponseUpdate]],
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Execute the agent middleware pipeline for streaming.

        Args:
            agent: The agent being invoked.
            messages: The messages to send to the agent.
            context: The agent invocation context.
            final_handler: The final handler that performs the actual agent streaming execution.

        Yields:
            Agent response updates after processing through all middleware.
        """
        # Update context with agent and messages
        context.agent = agent
        context.messages = messages
        context.is_streaming = True

        if not self._middlewares:
            async for update in final_handler(context):
                yield update
            return

        # Store the final result
        result_container: dict[str, AsyncIterable[AgentRunResponseUpdate] | None] = {"result_stream": None}

        first_handler = self._create_streaming_handler_chain(final_handler, result_container, "result_stream")
        await first_handler(context)

        # Yield from the result stream in result container or overridden result
        if context.result is not None and hasattr(context.result, "__aiter__"):
            async for update in context.result:  # type: ignore
                yield update
            return

        result_stream = result_container["result_stream"]
        if result_stream is None:
            # If no result stream was set (next() not called), yield nothing
            return

        async for update in result_stream:
            yield update


class FunctionMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes function middleware in a chain.

    Manages the execution of multiple function middleware in sequence, allowing each middleware
    to process the function invocation and pass control to the next middleware in the chain.
    """

    def __init__(self, middlewares: list[FunctionMiddleware | FunctionMiddlewareCallable] | None = None):
        """Initialize the function middleware pipeline.

        Args:
            middlewares: The list of function middleware to include in the pipeline.
        """
        super().__init__()
        self._middlewares: list[FunctionMiddleware] = []

        if middlewares:
            for middleware in middlewares:
                self._register_middleware(middleware)

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

        if not self._middlewares:
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

    def __init__(self, middlewares: list[ChatMiddleware | ChatMiddlewareCallable] | None = None):
        """Initialize the chat middleware pipeline.

        Args:
            middlewares: The list of chat middleware to include in the pipeline.
        """
        super().__init__()
        self._middlewares: list[ChatMiddleware] = []

        if middlewares:
            for middleware in middlewares:
                self._register_middleware(middleware)

    def _register_middleware(self, middleware: ChatMiddleware | ChatMiddlewareCallable) -> None:
        """Register a chat middleware item.

        Args:
            middleware: The chat middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, ChatMiddleware)

    async def execute(
        self,
        chat_client: "ChatClientProtocol",
        messages: "MutableSequence[ChatMessage]",
        chat_options: "ChatOptions",
        context: ChatContext,
        final_handler: Callable[[ChatContext], Awaitable["ChatResponse"]],
        **kwargs: Any,
    ) -> "ChatResponse":
        """Execute the chat middleware pipeline.

        Args:
            chat_client: The chat client being invoked.
            messages: The messages being sent to the chat client.
            chat_options: The options for the chat request.
            context: The chat invocation context.
            final_handler: The final handler that performs the actual chat execution.
            **kwargs: Additional keyword arguments.

        Returns:
            The chat response after processing through all middleware.
        """
        # Update context with chat client, messages, and options
        context.chat_client = chat_client
        context.messages = messages
        context.chat_options = chat_options

        if not self._middlewares:
            return await final_handler(context)

        # Store the final result
        result_container: dict[str, Any] = {"result": None}

        # Custom final handler that handles pre-existing results
        async def chat_final_handler(c: ChatContext) -> "ChatResponse":
            # If terminate was set, skip execution and return the result (which might be None)
            if c.terminate:
                return c.result  # type: ignore
            # Execute actual handler and populate context for observability
            return await final_handler(c)

        first_handler = self._create_handler_chain(chat_final_handler, result_container, "result")
        await first_handler(context)

        # Return the result from result container or overridden result
        if context.result is not None:
            return context.result  # type: ignore
        return result_container["result"]  # type: ignore

    async def execute_stream(
        self,
        chat_client: "ChatClientProtocol",
        messages: "MutableSequence[ChatMessage]",
        chat_options: "ChatOptions",
        context: ChatContext,
        final_handler: Callable[[ChatContext], AsyncIterable["ChatResponseUpdate"]],
        **kwargs: Any,
    ) -> AsyncIterable["ChatResponseUpdate"]:
        """Execute the chat middleware pipeline for streaming.

        Args:
            chat_client: The chat client being invoked.
            messages: The messages being sent to the chat client.
            chat_options: The options for the chat request.
            context: The chat invocation context.
            final_handler: The final handler that performs the actual streaming chat execution.
            **kwargs: Additional keyword arguments.

        Yields:
            Chat response updates after processing through all middleware.
        """
        # Update context with chat client, messages, and options
        context.chat_client = chat_client
        context.messages = messages
        context.chat_options = chat_options
        context.is_streaming = True

        if not self._middlewares:
            async for update in final_handler(context):
                yield update
            return

        # Store the final result stream
        result_container: dict[str, Any] = {"result_stream": None}

        first_handler = self._create_streaming_handler_chain(final_handler, result_container, "result_stream")
        await first_handler(context)

        # Yield from the result stream in result container or overridden result
        if context.result is not None and hasattr(context.result, "__aiter__"):
            async for update in context.result:  # type: ignore
                yield update
            return

        result_stream = result_container["result_stream"]
        if result_stream is None:
            # If no result stream was set (next() not called), yield nothing
            return

        async for update in result_stream:
            yield update


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
def use_agent_middleware(agent_class: type[TAgent]) -> type[TAgent]:
    """Class decorator that adds middleware support to an agent class.

    This decorator adds middleware functionality to any agent class.
    It wraps the ``run()`` and ``run_stream()`` methods to provide middleware execution.

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
                async def run(self, messages, **kwargs):
                    # Agent implementation
                    pass

                async def run_stream(self, messages, **kwargs):
                    # Streaming implementation
                    pass
    """
    # Store original methods
    original_run = agent_class.run  # type: ignore[attr-defined]
    original_run_stream = agent_class.run_stream  # type: ignore[attr-defined]

    def _build_middleware_pipelines(
        agent_level_middlewares: Middleware | list[Middleware] | None,
        run_level_middlewares: Middleware | list[Middleware] | None = None,
    ) -> tuple[AgentMiddlewarePipeline, FunctionMiddlewarePipeline, list[ChatMiddleware | ChatMiddlewareCallable]]:
        """Build fresh agent and function middleware pipelines from the provided middleware lists.

        Args:
            agent_level_middlewares: Agent-level middleware (executed first)
            run_level_middlewares: Run-level middleware (executed after agent middleware)
        """
        middleware = categorize_middleware(agent_level_middlewares, run_level_middlewares)

        return (
            AgentMiddlewarePipeline(middleware["agent"]),  # type: ignore[arg-type]
            FunctionMiddlewarePipeline(middleware["function"]),  # type: ignore[arg-type]
            middleware["chat"],  # type: ignore[return-value]
        )

    async def middleware_enabled_run(
        self: Any,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        middleware: Middleware | list[Middleware] | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Middleware-enabled run method."""
        # Build fresh middleware pipelines from current middleware collection and run-level middleware
        agent_middleware = getattr(self, "middleware", None)

        agent_pipeline, function_pipeline, chat_middlewares = _build_middleware_pipelines(agent_middleware, middleware)

        # Add function middleware pipeline to kwargs if available
        if function_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = function_pipeline

        # Pass chat middleware through kwargs for run-level application
        if chat_middlewares:
            kwargs["middleware"] = chat_middlewares

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if agent_pipeline.has_middlewares:
            context = AgentRunContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=False,
                kwargs=kwargs,
            )

            async def _execute_handler(ctx: AgentRunContext) -> AgentRunResponse:
                return await original_run(self, ctx.messages, thread=thread, **ctx.kwargs)  # type: ignore

            result = await agent_pipeline.execute(
                self,  # type: ignore[arg-type]
                normalized_messages,
                context,
                _execute_handler,
            )

            return result if result else AgentRunResponse()

        # No middleware, execute directly
        return await original_run(self, normalized_messages, thread=thread, **kwargs)  # type: ignore[return-value]

    def middleware_enabled_run_stream(
        self: Any,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        middleware: Middleware | list[Middleware] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Middleware-enabled run_stream method."""
        # Build fresh middleware pipelines from current middleware collection and run-level middleware
        agent_middleware = getattr(self, "middleware", None)
        agent_pipeline, function_pipeline, chat_middlewares = _build_middleware_pipelines(agent_middleware, middleware)

        # Add function middleware pipeline to kwargs if available
        if function_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = function_pipeline

        # Pass chat middleware through kwargs for run-level application
        if chat_middlewares:
            kwargs["middleware"] = chat_middlewares

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if agent_pipeline.has_middlewares:
            context = AgentRunContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=True,
                kwargs=kwargs,
            )

            async def _execute_stream_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
                async for update in original_run_stream(self, ctx.messages, thread=thread, **ctx.kwargs):  # type: ignore[misc]
                    yield update

            async def _stream_generator() -> AsyncIterable[AgentRunResponseUpdate]:
                async for update in agent_pipeline.execute_stream(
                    self,  # type: ignore[arg-type]
                    normalized_messages,
                    context,
                    _execute_stream_handler,
                ):
                    yield update

            return _stream_generator()

        # No middleware, execute directly
        return original_run_stream(self, normalized_messages, thread=thread, **kwargs)  # type: ignore

    agent_class.run = update_wrapper(middleware_enabled_run, original_run)  # type: ignore
    agent_class.run_stream = update_wrapper(middleware_enabled_run_stream, original_run_stream)  # type: ignore

    return agent_class


def use_chat_middleware(chat_client_class: type[TChatClient]) -> type[TChatClient]:
    """Class decorator that adds middleware support to a chat client class.

    This decorator adds middleware functionality to any chat client class.
    It wraps the ``get_response()`` and ``get_streaming_response()`` methods to provide middleware execution.

    Note:
        This decorator is already applied to built-in chat client classes. You only need to use
        it if you're creating custom chat client implementations.

    Args:
        chat_client_class: The chat client class to add middleware support to.

    Returns:
        The modified chat client class with middleware support.

    Examples:
        .. code-block:: python

            from agent_framework import use_chat_middleware


            @use_chat_middleware
            class CustomChatClient:
                async def get_response(self, messages, **kwargs):
                    # Chat client implementation
                    pass

                async def get_streaming_response(self, messages, **kwargs):
                    # Streaming implementation
                    pass
    """
    # Store original methods
    original_get_response = chat_client_class.get_response
    original_get_streaming_response = chat_client_class.get_streaming_response

    async def middleware_enabled_get_response(
        self: Any,
        messages: Any,
        **kwargs: Any,
    ) -> Any:
        """Middleware-enabled get_response method."""
        # Check if middleware is provided at call level or instance level
        call_middleware = kwargs.pop("middleware", None)
        instance_middleware = getattr(self, "middleware", None)

        # Merge all middleware and separate by type
        middleware = categorize_middleware(instance_middleware, call_middleware)
        chat_middleware_list = middleware["chat"]  # type: ignore[assignment]

        # Extract function middleware for the function invocation pipeline
        function_middleware_list = middleware["function"]

        # Pass function middleware to function invocation system if present
        if function_middleware_list:
            kwargs["_function_middleware_pipeline"] = FunctionMiddlewarePipeline(function_middleware_list)  # type: ignore[arg-type]

        # If no chat middleware, use original method
        if not chat_middleware_list:
            return await original_get_response(self, messages, **kwargs)

        # Create pipeline and execute with middleware
        from ._types import ChatOptions

        # Extract chat_options or create default
        chat_options = kwargs.pop("chat_options", ChatOptions())

        pipeline = ChatMiddlewarePipeline(chat_middleware_list)  # type: ignore[arg-type]
        context = ChatContext(
            chat_client=self,
            messages=self.prepare_messages(messages, chat_options),
            chat_options=chat_options,
            is_streaming=False,
            kwargs=kwargs,
        )

        async def final_handler(ctx: ChatContext) -> Any:
            return await original_get_response(self, list(ctx.messages), chat_options=ctx.chat_options, **ctx.kwargs)

        return await pipeline.execute(
            chat_client=self,
            messages=context.messages,
            chat_options=context.chat_options,
            context=context,
            final_handler=final_handler,
            **kwargs,
        )

    def middleware_enabled_get_streaming_response(
        self: Any,
        messages: Any,
        **kwargs: Any,
    ) -> Any:
        """Middleware-enabled get_streaming_response method."""

        async def _stream_generator() -> Any:
            # Check if middleware is provided at call level or instance level
            call_middleware = kwargs.pop("middleware", None)
            instance_middleware = getattr(self, "middleware", None)

            # Merge middleware from both sources, filtering for chat middleware only
            all_middleware: list[ChatMiddleware | ChatMiddlewareCallable] = _merge_and_filter_chat_middleware(
                instance_middleware, call_middleware
            )

            # If no middleware, use original method
            if not all_middleware:
                async for update in original_get_streaming_response(self, messages, **kwargs):
                    yield update
                return

            # Create pipeline and execute with middleware
            from ._types import ChatOptions

            # Extract chat_options or create default
            chat_options = kwargs.pop("chat_options", ChatOptions())

            pipeline = ChatMiddlewarePipeline(all_middleware)  # type: ignore[arg-type]
            context = ChatContext(
                chat_client=self,
                messages=self.prepare_messages(messages, chat_options),
                chat_options=chat_options,
                is_streaming=True,
                kwargs=kwargs,
            )

            def final_handler(ctx: ChatContext) -> Any:
                return original_get_streaming_response(
                    self, list(ctx.messages), chat_options=ctx.chat_options, **ctx.kwargs
                )

            async for update in pipeline.execute_stream(
                chat_client=self,
                messages=context.messages,
                chat_options=context.chat_options,
                context=context,
                final_handler=final_handler,
                **kwargs,
            ):
                yield update

        return _stream_generator()

    # Replace methods
    chat_client_class.get_response = update_wrapper(middleware_enabled_get_response, original_get_response)  # type: ignore
    chat_client_class.get_streaming_response = update_wrapper(  # type: ignore
        middleware_enabled_get_streaming_response, original_get_streaming_response
    )

    return chat_client_class


def categorize_middleware(
    *middleware_sources: Any | list[Any] | None,
) -> dict[str, list[Any]]:
    """Categorize middleware from multiple sources into agent, function, and chat types.

    Args:
        *middleware_sources: Variable number of middleware sources to categorize.

    Returns:
        Dict with keys "agent", "function", "chat" containing lists of categorized middleware.
    """
    result: dict[str, list[Any]] = {"agent": [], "function": [], "chat": []}

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
                result["agent"].append(middleware)
            elif middleware_type == MiddlewareType.FUNCTION:
                result["function"].append(middleware)
            elif middleware_type == MiddlewareType.CHAT:
                result["chat"].append(middleware)
        else:
            # Fallback to agent middleware for unknown types
            result["agent"].append(middleware)

    return result


def create_function_middleware_pipeline(
    *middleware_sources: list[Middleware] | None,
) -> FunctionMiddlewarePipeline | None:
    """Create a function middleware pipeline from multiple middleware sources.

    Args:
        *middleware_sources: Variable number of middleware sources.

    Returns:
        A FunctionMiddlewarePipeline if function middleware is found, None otherwise.
    """
    middleware = categorize_middleware(*middleware_sources)
    function_middlewares = middleware["function"]
    return FunctionMiddlewarePipeline(function_middlewares) if function_middlewares else None  # type: ignore[arg-type]


def _merge_and_filter_chat_middleware(
    instance_middleware: Any | list[Any] | None,
    call_middleware: Any | list[Any] | None,
) -> list[ChatMiddleware | ChatMiddlewareCallable]:
    """Merge instance-level and call-level middleware, filtering for chat middleware only.

    Args:
        instance_middleware: Middleware defined at the instance level.
        call_middleware: Middleware provided at the call level.

    Returns:
        A merged list of chat middleware only.
    """
    middleware = categorize_middleware(instance_middleware, call_middleware)
    return middleware["chat"]  # type: ignore[return-value]


def extract_and_merge_function_middleware(chat_client: Any, **kwargs: Any) -> None:
    """Extract function middleware from chat client and merge with existing pipeline in kwargs.

    Args:
        chat_client: The chat client instance to extract middleware from.

    Keyword Args:
        **kwargs: Dictionary containing middleware and pipeline information.
    """
    # Get middleware sources
    client_middleware = getattr(chat_client, "middleware", None) if hasattr(chat_client, "middleware") else None
    run_level_middleware = kwargs.get("middleware")
    existing_pipeline = kwargs.get("_function_middleware_pipeline")

    # Extract existing pipeline middlewares if present
    existing_middlewares = existing_pipeline._middlewares if existing_pipeline else None

    # Create combined pipeline from all sources using existing helper
    combined_pipeline = create_function_middleware_pipeline(
        client_middleware, run_level_middleware, existing_middlewares
    )

    if combined_pipeline:
        kwargs["_function_middleware_pipeline"] = combined_pipeline
