# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import contextlib
import inspect
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias, overload

from ._clients import SupportsChatGetResponse
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    ResponseStream,
    normalize_messages,
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

    from ._agents import SupportsAgentRun
    from ._clients import SupportsChatGetResponse
    from ._sessions import AgentSession
    from ._tools import FunctionTool
    from ._types import ChatOptions, ChatResponse, ChatResponseUpdate

    ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)


AgentT = TypeVar("AgentT", bound="SupportsAgentRun")
ContextT = TypeVar("ContextT")
UpdateT = TypeVar("UpdateT")


class _EmptyAsyncIterator(Generic[UpdateT]):
    """Empty async iterator that yields nothing.

    Used when middleware terminates without setting a result,
    and we need to provide an empty stream.
    """

    def __aiter__(self) -> _EmptyAsyncIterator[UpdateT]:
        return self

    async def __anext__(self) -> UpdateT:
        raise StopAsyncIteration


def _empty_async_iterable() -> AsyncIterable[Any]:
    """Create an empty async iterable that yields nothing."""
    return _EmptyAsyncIterator()


class MiddlewareTermination(MiddlewareException):
    """Control-flow exception to terminate middleware execution early."""

    result: Any = None  # Optional result to return when terminating

    def __init__(self, message: str = "Middleware terminated execution.", *, result: Any = None) -> None:
        super().__init__(message, log_level=None)
        self.result = result


class MiddlewareType(str, Enum):
    """Enum representing the type of middleware.

    Used internally to identify and categorize middleware types.
    """

    AGENT = "agent"
    FUNCTION = "function"
    CHAT = "chat"


class AgentContext:
    """Context object for agent middleware invocations.

    This context is passed through the agent middleware pipeline and contains all information
    about the agent invocation.

    Attributes:
        agent: The agent being invoked.
        messages: The messages being sent to the agent.
        session: The agent session for this invocation, if any.
        options: The options for the agent invocation as a dict.
        stream: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between agent middleware.
        result: Agent execution result. Can be observed after calling ``call_next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be AgentResponse.
                For streaming: should be ResponseStream[AgentResponseUpdate, AgentResponse].
        kwargs: Additional keyword arguments passed to the agent run method.

    Examples:
        .. code-block:: python

            from agent_framework import AgentMiddleware, AgentContext


            class LoggingMiddleware(AgentMiddleware):
                async def process(self, context: AgentContext, call_next):
                    print(f"Agent: {context.agent.name}")
                    print(f"Messages: {len(context.messages)}")
                    print(f"Session: {context.session}")
                    print(f"Streaming: {context.stream}")

                    # Store metadata
                    context.metadata["start_time"] = time.time()

                    # Continue execution
                    await call_next()

                    # Access result after execution
                    print(f"Result: {context.result}")
    """

    def __init__(
        self,
        *,
        agent: SupportsAgentRun,
        messages: list[Message],
        session: AgentSession | None = None,
        options: Mapping[str, Any] | None = None,
        stream: bool = False,
        metadata: Mapping[str, Any] | None = None,
        result: AgentResponse | ResponseStream[AgentResponseUpdate, AgentResponse] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        stream_transform_hooks: Sequence[
            Callable[[AgentResponseUpdate], AgentResponseUpdate | Awaitable[AgentResponseUpdate]]
        ]
        | None = None,
        stream_result_hooks: Sequence[Callable[[AgentResponse], AgentResponse | Awaitable[AgentResponse]]]
        | None = None,
        stream_cleanup_hooks: Sequence[Callable[[], Awaitable[None] | None]] | None = None,
    ) -> None:
        """Initialize the AgentContext.

        Args:
            agent: The agent being invoked.
            messages: The messages being sent to the agent.
            session: The agent session for this invocation, if any.
            options: The options for the agent invocation as a dict.
            stream: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between agent middleware.
            result: Agent execution result.
            kwargs: Additional keyword arguments passed to the agent run method.
            stream_transform_hooks: Hooks to transform streamed updates.
            stream_result_hooks: Hooks to process the final result after streaming.
            stream_cleanup_hooks: Hooks to run after streaming completes.
        """
        self.agent = agent
        self.messages = messages
        self.session = session
        self.options = options
        self.stream = stream
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.kwargs = kwargs if kwargs is not None else {}
        self.stream_transform_hooks = list(stream_transform_hooks or [])
        self.stream_result_hooks = list(stream_result_hooks or [])
        self.stream_cleanup_hooks = list(stream_cleanup_hooks or [])


class FunctionInvocationContext:
    """Context object for function middleware invocations.

    This context is passed through the function middleware pipeline and contains all information
    about the function invocation.

    Attributes:
        function: The function being invoked.
        arguments: The validated arguments for the function.
        metadata: Metadata dictionary for sharing data between function middleware.
        result: Function execution result. Can be observed after calling ``call_next()``
                to see the actual execution result or can be set to override the execution result.

        kwargs: Additional keyword arguments passed to the chat method that invoked this function.

    Examples:
        .. code-block:: python

            from agent_framework import FunctionMiddleware, FunctionInvocationContext


            class ValidationMiddleware(FunctionMiddleware):
                async def process(self, context: FunctionInvocationContext, call_next):
                    print(f"Function: {context.function.name}")
                    print(f"Arguments: {context.arguments}")

                    # Validate arguments
                    if not self.validate(context.arguments):
                        raise MiddlewareTermination("Validation failed")

                    # Continue execution
                    await call_next()
    """

    def __init__(
        self,
        function: FunctionTool,
        arguments: BaseModel | Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        result: Any = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the FunctionInvocationContext.

        Args:
            function: The function being invoked.
            arguments: The validated arguments for the function.
            metadata: Metadata dictionary for sharing data between function middleware.
            result: Function execution result.
            kwargs: Additional keyword arguments passed to the chat method that invoked this function.
        """
        self.function = function
        self.arguments = arguments
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.kwargs = kwargs if kwargs is not None else {}


class ChatContext:
    """Context object for chat middleware invocations.

    This context is passed through the chat middleware pipeline and contains all information
    about the chat request.

    Attributes:
        client: The chat client being invoked.
        messages: The messages being sent to the chat client.
        options: The options for the chat request as a dict.
        stream: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between chat middleware.
        result: Chat execution result. Can be observed after calling ``call_next()``
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be ChatResponse.
                For streaming: should be ResponseStream[ChatResponseUpdate, ChatResponse].
        kwargs: Additional keyword arguments passed to the chat client.
        stream_transform_hooks: Hooks applied to transform each streamed update.
        stream_result_hooks: Hooks applied to the finalized response (after finalizer).
        stream_cleanup_hooks: Hooks executed after stream consumption (before finalizer).

    Examples:
        .. code-block:: python

            from agent_framework import ChatMiddleware, ChatContext


            class TokenCounterMiddleware(ChatMiddleware):
                async def process(self, context: ChatContext, call_next):
                    print(f"Chat client: {context.chat_client.__class__.__name__}")
                    print(f"Messages: {len(context.messages)}")
                    print(f"Model: {context.options.get('model_id')}")

                    # Store metadata
                    context.metadata["input_tokens"] = self.count_tokens(context.messages)

                    # Continue execution
                    await call_next()

                    # Access result and count output tokens
                    if context.result:
                        context.metadata["output_tokens"] = self.count_tokens(context.result)
    """

    def __init__(
        self,
        client: SupportsChatGetResponse,
        messages: Sequence[Message],
        options: Mapping[str, Any] | None,
        stream: bool = False,
        metadata: Mapping[str, Any] | None = None,
        result: ChatResponse | ResponseStream[ChatResponseUpdate, ChatResponse] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        stream_transform_hooks: Sequence[
            Callable[[ChatResponseUpdate], ChatResponseUpdate | Awaitable[ChatResponseUpdate]]
        ]
        | None = None,
        stream_result_hooks: Sequence[Callable[[ChatResponse], ChatResponse | Awaitable[ChatResponse]]] | None = None,
        stream_cleanup_hooks: Sequence[Callable[[], Awaitable[None] | None]] | None = None,
    ) -> None:
        """Initialize the ChatContext.

        Args:
            client: The chat client being invoked.
            messages: The messages being sent to the chat client.
            options: The options for the chat request as a dict.
            stream: Whether this is a streaming invocation.
            metadata: Metadata dictionary for sharing data between chat middleware.
            result: Chat execution result.
            kwargs: Additional keyword arguments passed to the chat client.
            stream_transform_hooks: Transform hooks to apply to each streamed update.
            stream_result_hooks: Result hooks to apply to the finalized streaming response.
            stream_cleanup_hooks: Cleanup hooks to run after streaming completes.
        """
        self.client = client
        self.messages = messages
        self.options = options
        self.stream = stream
        self.metadata = metadata if metadata is not None else {}
        self.result = result
        self.kwargs = kwargs if kwargs is not None else {}
        self.stream_transform_hooks = list(stream_transform_hooks or [])
        self.stream_result_hooks = list(stream_result_hooks or [])
        self.stream_cleanup_hooks = list(stream_cleanup_hooks or [])


class AgentMiddleware(ABC):
    """Abstract base class for agent middleware that can intercept agent invocations.

    Agent middleware allows you to intercept and modify agent invocations before and after
    execution. You can inspect messages, modify context, override results, or raise
    ``MiddlewareTermination`` to terminate execution early.

    Note:
        AgentMiddleware is an abstract base class. You must subclass it and implement
        the ``process()`` method to create custom agent middleware.

    Examples:
        .. code-block:: python

            from agent_framework import AgentMiddleware, AgentContext, Agent


            class RetryMiddleware(AgentMiddleware):
                def __init__(self, max_retries: int = 3):
                    self.max_retries = max_retries

                async def process(self, context: AgentContext, call_next):
                    for attempt in range(self.max_retries):
                        await call_next()
                        if context.result and not context.result.is_error:
                            break
                        print(f"Retry {attempt + 1}/{self.max_retries}")


            # Use with an agent
            agent = Agent(client=client, name="assistant", middleware=[RetryMiddleware()])
    """

    @abstractmethod
    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Process an agent invocation.

        Args:
            context: Agent invocation context containing agent, messages, and metadata.
                    Use context.stream to determine if this is a streaming call.
                    MiddlewareTypes can set context.result to override execution, or observe
                    the actual execution result after calling call_next().
                    For non-streaming: AgentResponse
                    For streaming: AsyncIterable[AgentResponseUpdate]
            call_next: Function to call the next middleware or final agent execution.
                  Does not return anything - all data flows through the context.

        Note:
            MiddlewareTypes should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling call_next() for actual results.
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

            from agent_framework import FunctionMiddleware, FunctionInvocationContext, Agent


            class CachingMiddleware(FunctionMiddleware):
                def __init__(self):
                    self.cache = {}

                async def process(self, context: FunctionInvocationContext, call_next):
                    cache_key = f"{context.function.name}:{context.arguments}"

                    # Check cache
                    if cache_key in self.cache:
                        context.result = self.cache[cache_key]
                        raise MiddlewareTermination()

                    # Execute function
                    await call_next()

                    # Cache result
                    if context.result:
                        self.cache[cache_key] = context.result


            # Use with an agent
            agent = Agent(client=client, name="assistant", middleware=[CachingMiddleware()])
    """

    @abstractmethod
    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Process a function invocation.

        Args:
            context: Function invocation context containing function, arguments, and metadata.
                    MiddlewareTypes can set context.result to override execution, or observe
                    the actual execution result after calling call_next().
            call_next: Function to call the next middleware or final function execution.
                  Does not return anything - all data flows through the context.

        Note:
            MiddlewareTypes should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling call_next() for actual results.
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

            from agent_framework import ChatMiddleware, ChatContext, Agent


            class SystemPromptMiddleware(ChatMiddleware):
                def __init__(self, system_prompt: str):
                    self.system_prompt = system_prompt

                async def process(self, context: ChatContext, call_next):
                    # Add system prompt to messages
                    from agent_framework import Message

                    context.messages.insert(0, Message(role="system", text=self.system_prompt))

                    # Continue execution
                    await call_next()


            # Use with an agent
            agent = Agent(
                client=client,
                name="assistant",
                middleware=[SystemPromptMiddleware("You are a helpful assistant.")],
            )
    """

    @abstractmethod
    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Process a chat client request.

        Args:
            context: Chat invocation context containing chat client, messages, options, and metadata.
                    Use context.stream to determine if this is a streaming call.
                    MiddlewareTypes can set context.result to override execution, or observe
                    the actual execution result after calling call_next().
                    For non-streaming: ChatResponse
                    For streaming: ResponseStream[ChatResponseUpdate, ChatResponse]
            call_next: Function to call the next middleware or final chat execution.
                  Does not return anything - all data flows through the context.

        Note:
            MiddlewareTypes should not return anything. All data manipulation should happen
            within the context object. Set context.result to override execution,
            or observe context.result after calling call_next() for actual results.
        """
        ...


# Pure function type definitions for convenience
AgentMiddlewareCallable = Callable[[AgentContext, Callable[[], Awaitable[None]]], Awaitable[None]]
AgentMiddlewareTypes: TypeAlias = AgentMiddleware | AgentMiddlewareCallable

FunctionMiddlewareCallable = Callable[[FunctionInvocationContext, Callable[[], Awaitable[None]]], Awaitable[None]]
FunctionMiddlewareTypes: TypeAlias = FunctionMiddleware | FunctionMiddlewareCallable

ChatMiddlewareCallable = Callable[[ChatContext, Callable[[], Awaitable[None]]], Awaitable[None]]
ChatMiddlewareTypes: TypeAlias = ChatMiddleware | ChatMiddlewareCallable

ChatAndFunctionMiddlewareTypes: TypeAlias = (
    FunctionMiddleware | FunctionMiddlewareCallable | ChatMiddleware | ChatMiddlewareCallable
)

# Type alias for all middleware types
MiddlewareTypes: TypeAlias = (
    AgentMiddleware
    | AgentMiddlewareCallable
    | FunctionMiddleware
    | FunctionMiddlewareCallable
    | ChatMiddleware
    | ChatMiddlewareCallable
)


def agent_middleware(func: AgentMiddlewareCallable) -> AgentMiddlewareCallable:
    """Decorator to mark a function as agent middleware.

    This decorator explicitly identifies a function as agent middleware,
    which processes AgentContext objects.

    Args:
        func: The middleware function to mark as agent middleware.

    Returns:
        The same function with agent middleware marker.

    Examples:
        .. code-block:: python

            from agent_framework import agent_middleware, AgentContext, Agent


            @agent_middleware
            async def logging_middleware(context: AgentContext, call_next):
                print(f"Before: {context.agent.name}")
                await call_next()
                print(f"After: {context.result}")


            # Use with an agent
            agent = Agent(client=client, name="assistant", middleware=[logging_middleware])
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

            from agent_framework import function_middleware, FunctionInvocationContext, Agent


            @function_middleware
            async def logging_middleware(context: FunctionInvocationContext, call_next):
                print(f"Calling: {context.function.name}")
                await call_next()
                print(f"Result: {context.result}")


            # Use with an agent
            agent = Agent(client=client, name="assistant", middleware=[logging_middleware])
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

            from agent_framework import chat_middleware, ChatContext, Agent


            @chat_middleware
            async def logging_middleware(context: ChatContext, call_next):
                print(f"Messages: {len(context.messages)}")
                await call_next()
                print(f"Response: {context.result}")


            # Use with an agent
            agent = Agent(client=client, name="assistant", middleware=[logging_middleware])
    """
    # Add marker attribute to identify this as chat middleware
    func._middleware_type: MiddlewareType = MiddlewareType.CHAT  # type: ignore
    return func


class MiddlewareWrapper(Generic[ContextT]):
    """Generic wrapper to convert pure functions into middleware protocol objects.

    This wrapper allows function-based middleware to be used alongside class-based middleware
    by providing a unified interface.

    Type Parameters:
        ContextT: The type of context object this middleware operates on.
    """

    def __init__(self, func: Callable[[ContextT, Callable[[], Awaitable[None]]], Awaitable[None]]) -> None:
        self.func = func

    async def process(self, context: ContextT, call_next: Callable[[], Awaitable[None]]) -> None:
        await self.func(context, call_next)


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


class AgentMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes agent middleware in a chain.

    Manages the execution of multiple agent middleware in sequence, allowing each middleware
    to process the agent invocation and pass control to the next middleware in the chain.
    """

    def __init__(self, *middleware: AgentMiddlewareTypes):
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
        context: AgentContext,
        final_handler: Callable[
            [AgentContext], Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]
        ],
    ) -> AgentResponse | ResponseStream[AgentResponseUpdate, AgentResponse] | None:
        """Execute the agent middleware pipeline for streaming or non-streaming.

        Args:
            context: The agent invocation context.
            final_handler: The final handler that performs the actual agent execution.

        Returns:
            The agent response after processing through all middleware.
        """
        if not self._middleware:
            context.result = final_handler(context)  # type: ignore[assignment]
            if isinstance(context.result, Awaitable):
                context.result = await context.result
            return context.result

        def create_next_handler(index: int) -> Callable[[], Awaitable[None]]:
            if index >= len(self._middleware):

                async def final_wrapper() -> None:
                    context.result = final_handler(context)  # type: ignore[assignment]
                    if inspect.isawaitable(context.result):
                        context.result = await context.result

                return final_wrapper

            async def current_handler() -> None:
                # MiddlewareTermination bubbles up to execute() to skip post-processing
                await self._middleware[index].process(context, create_next_handler(index + 1))

            return current_handler

        first_handler = create_next_handler(0)
        with contextlib.suppress(MiddlewareTermination):
            await first_handler()

        if context.result and isinstance(context.result, ResponseStream):
            for hook in context.stream_transform_hooks:
                context.result.with_transform_hook(hook)
            for result_hook in context.stream_result_hooks:
                context.result.with_result_hook(result_hook)
            for cleanup_hook in context.stream_cleanup_hooks:
                context.result.with_cleanup_hook(cleanup_hook)
        return context.result


class FunctionMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes function middleware in a chain.

    Manages the execution of multiple function middleware in sequence, allowing each middleware
    to process the function invocation and pass control to the next middleware in the chain.
    """

    def __init__(self, *middleware: FunctionMiddlewareTypes):
        """Initialize the function middleware pipeline.

        Args:
            middleware: The list of function middleware to include in the pipeline.
        """
        super().__init__()
        self._middleware: list[FunctionMiddleware] = []

        if middleware:
            for mdlware in middleware:
                self._register_middleware(mdlware)

    def _register_middleware(self, middleware: FunctionMiddlewareTypes) -> None:
        """Register a function middleware item.

        Args:
            middleware: The function middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, FunctionMiddleware)

    async def execute(
        self,
        context: FunctionInvocationContext,
        final_handler: Callable[[FunctionInvocationContext], Awaitable[Any]],
    ) -> Any:
        """Execute the function middleware pipeline.

        Args:
            context: The function invocation context.
            final_handler: The final handler that performs the actual function execution.

        Returns:
            The function result after processing through all middleware.
        """
        if not self._middleware:
            return await final_handler(context)

        def create_next_handler(index: int) -> Callable[[], Awaitable[None]]:
            if index >= len(self._middleware):

                async def final_wrapper() -> None:
                    context.result = final_handler(context)
                    if inspect.isawaitable(context.result):
                        context.result = await context.result

                return final_wrapper

            async def current_handler() -> None:
                # MiddlewareTermination bubbles up to execute() to skip post-processing
                await self._middleware[index].process(context, create_next_handler(index + 1))

            return current_handler

        first_handler = create_next_handler(0)
        # Don't suppress MiddlewareTermination - let it propagate to signal loop termination
        await first_handler()

        return context.result


class ChatMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes chat middleware in a chain.

    Manages the execution of multiple chat middleware in sequence, allowing each middleware
    to process the chat request and pass control to the next middleware in the chain.
    """

    def __init__(self, *middleware: ChatMiddlewareTypes):
        """Initialize the chat middleware pipeline.

        Args:
            middleware: The list of chat middleware to include in the pipeline.
        """
        super().__init__()
        self._middleware: list[ChatMiddleware] = []

        if middleware:
            for mdlware in middleware:
                self._register_middleware(mdlware)

    def _register_middleware(self, middleware: ChatMiddlewareTypes) -> None:
        """Register a chat middleware item.

        Args:
            middleware: The chat middleware to register.
        """
        self._register_middleware_with_wrapper(middleware, ChatMiddleware)

    async def execute(
        self,
        context: ChatContext,
        final_handler: Callable[
            [ChatContext], Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]
        ],
    ) -> ChatResponse | ResponseStream[ChatResponseUpdate, ChatResponse] | None:
        """Execute the chat middleware pipeline.

        Args:
            context: The chat invocation context.
            final_handler: The final handler that performs the actual chat execution.

        Returns:
            The chat response after processing through all middleware.
        """
        if not self._middleware:
            context.result = final_handler(context)  # type: ignore[assignment]
            if isinstance(context.result, Awaitable):
                context.result = await context.result
            if context.stream and not isinstance(context.result, ResponseStream):
                raise ValueError("Streaming agent middleware requires a ResponseStream result.")
            return context.result

        def create_next_handler(index: int) -> Callable[[], Awaitable[None]]:
            if index >= len(self._middleware):

                async def final_wrapper() -> None:
                    context.result = final_handler(context)  # type: ignore[assignment]
                    if inspect.isawaitable(context.result):
                        context.result = await context.result

                return final_wrapper

            async def current_handler() -> None:
                # MiddlewareTermination bubbles up to execute() to skip post-processing
                await self._middleware[index].process(context, create_next_handler(index + 1))

            return current_handler

        first_handler = create_next_handler(0)
        with contextlib.suppress(MiddlewareTermination):
            await first_handler()

        if context.result and isinstance(context.result, ResponseStream):
            for hook in context.stream_transform_hooks:
                context.result.with_transform_hook(hook)
            for result_hook in context.stream_result_hooks:
                context.result.with_result_hook(result_hook)
            for cleanup_hook in context.stream_cleanup_hooks:
                context.result.with_cleanup_hook(cleanup_hook)
        return context.result


# Covariant for chat client options
OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class ChatMiddlewareLayer(Generic[OptionsCoT]):
    """Layer for chat clients to apply chat middleware around response generation."""

    def __init__(
        self,
        *,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> None:
        middleware_list = categorize_middleware(*(middleware or []))
        self.chat_middleware = middleware_list["chat"]
        if "function_middleware" in kwargs and middleware_list["function"]:
            raise ValueError("Cannot specify 'function_middleware' and 'middleware' at the same time.")
        kwargs["function_middleware"] = middleware_list["function"]
        super().__init__(**kwargs)

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Execute the chat pipeline if middleware is configured."""
        super_get_response = super().get_response  # type: ignore[misc]

        call_middleware = kwargs.pop("middleware", [])
        middleware = categorize_middleware(call_middleware)
        kwargs["function_middleware"] = middleware["function"]

        pipeline = ChatMiddlewarePipeline(
            *self.chat_middleware,
            *middleware["chat"],
        )
        if not pipeline.has_middlewares:
            return super_get_response(  # type: ignore[no-any-return]
                messages=messages,
                stream=stream,
                options=options,
                **kwargs,
            )

        context = ChatContext(
            client=self,  # type: ignore[arg-type]
            messages=list(messages),
            options=options,
            stream=stream,
            kwargs=kwargs,
        )

        async def _execute() -> ChatResponse | ResponseStream[ChatResponseUpdate, ChatResponse] | None:
            return await pipeline.execute(
                context=context,
                final_handler=self._middleware_handler,
            )

        if stream:
            # For streaming, wrap execution in ResponseStream.from_awaitable
            async def _execute_stream() -> ResponseStream[ChatResponseUpdate, ChatResponse]:
                result = await _execute()
                if result is None:
                    # Create empty stream if middleware terminated without setting result
                    return ResponseStream(_empty_async_iterable())
                if isinstance(result, ResponseStream):
                    return result
                # If result is ChatResponse (shouldn't happen for streaming), raise error
                raise ValueError("Expected ResponseStream for streaming, got ChatResponse")

            return ResponseStream.from_awaitable(_execute_stream())

        # For non-streaming, return the coroutine directly
        return _execute()  # type: ignore[return-value]

    def _middleware_handler(
        self, context: ChatContext
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Internal middleware handler to adapt to pipeline."""
        return super().get_response(  # type: ignore[misc, no-any-return]
            messages=context.messages,
            stream=context.stream,
            options=context.options or {},
            **context.kwargs,
        )


class AgentMiddlewareLayer:
    """Layer for agents to apply agent middleware around run execution."""

    def __init__(
        self,
        *args: Any,
        middleware: Sequence[MiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> None:
        middleware_list = categorize_middleware(middleware)
        self.agent_middleware = middleware_list["agent"]
        # Pass middleware to super so BaseAgent can store it for dynamic rebuild
        super().__init__(*args, middleware=middleware, **kwargs)  # type: ignore[call-arg]
        # Note: We intentionally don't extend client's middleware lists here.
        # Chat and function middleware is passed to the chat client at runtime via kwargs
        # in AgentMiddlewareLayer.run(), where it's properly combined with run-level middleware.

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[ResponseModelBoundT]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        options: ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        options: ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        options: ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """MiddlewareTypes-enabled unified run method."""
        # Re-categorize self.middleware at runtime to support dynamic changes
        base_middleware = getattr(self, "middleware", None) or []
        base_middleware_list = categorize_middleware(base_middleware)
        run_middleware_list = categorize_middleware(middleware)
        pipeline = AgentMiddlewarePipeline(*base_middleware_list["agent"], *run_middleware_list["agent"])

        # Combine base and run-level function/chat middleware for forwarding to chat client
        combined_function_chat_middleware = (
            base_middleware_list["function"]
            + base_middleware_list["chat"]
            + run_middleware_list["function"]
            + run_middleware_list["chat"]
        )
        combined_kwargs = dict(kwargs)
        combined_kwargs["middleware"] = combined_function_chat_middleware if combined_function_chat_middleware else None

        # Execute with middleware if available
        if not pipeline.has_middlewares:
            return super().run(messages, stream=stream, session=session, options=options, **combined_kwargs)  # type: ignore[misc, no-any-return]

        context = AgentContext(
            agent=self,  # type: ignore[arg-type]
            messages=normalize_messages(messages),
            session=session,
            options=options,
            stream=stream,
            kwargs=combined_kwargs,
        )

        async def _execute() -> AgentResponse | ResponseStream[AgentResponseUpdate, AgentResponse] | None:
            return await pipeline.execute(
                context=context,
                final_handler=self._middleware_handler,
            )

        if stream:
            # For streaming, wrap execution in ResponseStream.from_awaitable
            async def _execute_stream() -> ResponseStream[AgentResponseUpdate, AgentResponse]:
                result = await _execute()
                if result is None:
                    # Create empty stream if middleware terminated without setting result
                    return ResponseStream(_empty_async_iterable())
                if isinstance(result, ResponseStream):
                    return result
                # If result is AgentResponse (shouldn't happen for streaming), convert to stream
                raise ValueError("Expected ResponseStream for streaming, got AgentResponse")

            return ResponseStream.from_awaitable(_execute_stream())

        # For non-streaming, return the coroutine directly
        return _execute()  # type: ignore[return-value]

    def _middleware_handler(
        self, context: AgentContext
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        return super().run(  # type: ignore[misc, no-any-return]
            context.messages,
            stream=context.stream,
            session=context.session,
            options=context.options,
            **context.kwargs,
        )


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

        # Must have at least 2 parameters (context and call_next)
        if len(params) >= 2:
            first_param = params[0]
            if hasattr(first_param.annotation, "__name__"):
                annotation_name = first_param.annotation.__name__
                if annotation_name == "AgentContext":
                    param_type = MiddlewareType.AGENT
                elif annotation_name == "FunctionInvocationContext":
                    param_type = MiddlewareType.FUNCTION
                elif annotation_name == "ChatContext":
                    param_type = MiddlewareType.CHAT
        else:
            # Not enough parameters - can't be valid middleware
            raise MiddlewareException(
                f"Middleware function must have at least 2 parameters (context, call_next), "
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
                f"MiddlewareTypes type mismatch: decorator indicates '{decorator_type.value}' "
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
        f"or specify parameter types (AgentContext, FunctionInvocationContext, or ChatContext)."
    )


class MiddlewareDict(TypedDict):
    agent: list[AgentMiddleware | AgentMiddlewareCallable]
    function: list[FunctionMiddleware | FunctionMiddlewareCallable]
    chat: list[ChatMiddleware | ChatMiddlewareCallable]


def categorize_middleware(
    *middleware_sources: MiddlewareTypes | Sequence[MiddlewareTypes] | None,
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
