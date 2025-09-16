# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from ._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage

if TYPE_CHECKING:
    from pydantic import BaseModel

    from ._agents import AgentProtocol
    from ._tools import AIFunction

TAgent = TypeVar("TAgent", bound="AgentProtocol")

__all__ = [
    "AgentInvocationContext",
    "AgentMiddleware",
    "FunctionInvocationContext",
    "FunctionMiddleware",
    "MiddlewareType",
    "use_agent_middleware",
]


class AgentInvocationContext:
    """Context object for agent middleware invocations.

    Attributes:
        agent: The agent being invoked.
        messages: The messages being sent to the agent.
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between agent middleware.
    """

    def __init__(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        is_streaming: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize agent invocation context.

        Args:
            agent: The agent being invoked.
            messages: The messages being sent to the agent.
            is_streaming: Whether this is a streaming invocation.
            metadata: Metadata dictionary.
        """
        self.agent = agent
        self.messages = messages
        self.is_streaming = is_streaming
        self.metadata = metadata or {}


class FunctionInvocationContext:
    """Context object for function middleware invocations.

    Attributes:
        function: The function being invoked.
        arguments: The validated arguments for the function.
        metadata: Metadata dictionary for sharing data between function middleware.
    """

    def __init__(
        self,
        function: "AIFunction[Any, Any]",
        arguments: "BaseModel",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize function invocation context.

        Args:
            function: The function being invoked.
            arguments: The validated arguments for the function.
            metadata: Metadata dictionary.
        """
        self.function = function
        self.arguments = arguments
        self.metadata = metadata or {}


class AgentMiddleware(ABC):
    """Abstract base class for agent middleware that can intercept agent invocations."""

    @abstractmethod
    async def process(
        self,
        context: AgentInvocationContext,
        next: Callable[[AgentInvocationContext], Awaitable[None]],
    ) -> None:
        """Process an agent invocation.

        Args:
            context: Agent invocation context containing agent, messages, and metadata.
                    Use context.is_streaming to determine if this is a streaming call.
                    Middleware can set context.should_skip=True and provide context.response
                    or context.response_stream to override the agent execution.
            next: Function to call the next middleware or final agent execution.
                  Does not return anything - all data flows through the context.

        Note:
            Middleware should not return anything. All data manipulation should happen
            within the context object. Set context.should_skip=True and provide
            context.response or context.response_stream to override execution.
        """
        ...


class FunctionMiddleware(ABC):
    """Abstract base class for function middleware that can intercept function invocations."""

    @abstractmethod
    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Process a function invocation.

        Args:
            context: Function invocation context containing function, arguments, and metadata.
                    Middleware can set context.should_skip=True and provide context.result
                    to override the function execution.
            next: Function to call the next middleware or final function execution.
                  Does not return anything - all data flows through the context.

        Note:
            Middleware should not return anything. All data manipulation should happen
            within the context object. Set context.should_skip=True and provide
            context.result to override execution.
        """
        ...


# Pure function type definitions for convenience
AgentMiddlewareCallable = Callable[
    [AgentInvocationContext, Callable[[AgentInvocationContext], Awaitable[None]]], Awaitable[None]
]

FunctionMiddlewareCallable = Callable[
    [FunctionInvocationContext, Callable[[FunctionInvocationContext], Awaitable[None]]], Awaitable[None]
]

# Type alias for all middleware types
MiddlewareType = AgentMiddleware | AgentMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable


class AgentMiddlewareWrapper(AgentMiddleware):
    """Wrapper to convert pure functions into AgentMiddleware protocol objects."""

    def __init__(self, func: AgentMiddlewareCallable):
        self.func = func

    async def process(
        self,
        context: AgentInvocationContext,
        next: Callable[[AgentInvocationContext], Awaitable[None]],
    ) -> None:
        await self.func(context, next)


class FunctionMiddlewareWrapper(FunctionMiddleware):
    """Wrapper to convert pure functions into FunctionMiddleware protocol objects."""

    def __init__(self, func: FunctionMiddlewareCallable):
        self.func = func

    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        await self.func(context, next)


class AgentMiddlewarePipeline:
    """Executes agent middleware in a chain."""

    def __init__(self, middlewares: list[AgentMiddleware | AgentMiddlewareCallable] | None = None):
        """Initialize the agent middleware pipeline.

        Args:
            middlewares: List of agent middleware to include in the pipeline.
        """
        self._middlewares: list[AgentMiddleware] = []

        if middlewares:
            for middleware in middlewares:
                self._register_middleware(middleware)

    def _register_middleware(self, middleware: AgentMiddleware | AgentMiddlewareCallable) -> None:
        """Register an agent middleware item."""
        if isinstance(middleware, AgentMiddleware):
            self._middlewares.append(middleware)
        elif callable(middleware):
            self._middlewares.append(AgentMiddlewareWrapper(middleware))

    async def execute(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        context: AgentInvocationContext,
        final_handler: Callable[[AgentInvocationContext], Awaitable[AgentRunResponse]],
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
        result_container: dict[str, AgentRunResponse | None] = {"response": None}

        def create_next_handler(index: int) -> Callable[[AgentInvocationContext], Awaitable[None]]:
            if index >= len(self._middlewares):

                async def final_wrapper(c: AgentInvocationContext) -> None:
                    result_container["response"] = await final_handler(c)

                return final_wrapper

            middleware = self._middlewares[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: AgentInvocationContext) -> None:
                await middleware.process(c, next_handler)

            return current_handler

        first_handler = create_next_handler(0)
        await first_handler(context)

        # Return the response from result container
        return result_container["response"]

    async def execute_stream(
        self,
        agent: "AgentProtocol",
        messages: list[ChatMessage],
        context: AgentInvocationContext,
        final_handler: Callable[[AgentInvocationContext], AsyncIterable[AgentRunResponseUpdate]],
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
        result_container: dict[str, AsyncIterable[AgentRunResponseUpdate] | None] = {"response_stream": None}

        def create_next_handler(index: int) -> Callable[[AgentInvocationContext], Awaitable[None]]:
            if index >= len(self._middlewares):

                async def final_wrapper(c: AgentInvocationContext) -> None:  # noqa: RUF029
                    result_container["response_stream"] = final_handler(c)

                return final_wrapper

            middleware = self._middlewares[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: AgentInvocationContext) -> None:
                await middleware.process(c, next_handler)

            return current_handler

        first_handler = create_next_handler(0)
        await first_handler(context)

        # Yield from the response stream in result container
        response_stream = result_container["response_stream"]
        if response_stream is None:
            raise RuntimeError("No response stream set after middleware execution")

        async for update in response_stream:
            yield update

    @property
    def has_middlewares(self) -> bool:
        """Check if there are any middlewares registered."""
        return bool(self._middlewares)


class FunctionMiddlewarePipeline:
    """Executes function middleware in a chain."""

    def __init__(self, middlewares: list[FunctionMiddleware | FunctionMiddlewareCallable] | None = None):
        """Initialize the function middleware pipeline.

        Args:
            middlewares: List of function middleware to include in the pipeline.
        """
        self._middlewares: list[FunctionMiddleware] = []

        if middlewares:
            for middleware in middlewares:
                self._register_middleware(middleware)

    def _register_middleware(self, middleware: FunctionMiddleware | FunctionMiddlewareCallable) -> None:
        """Register a function middleware item."""
        # Check if it's a class instance inheriting from FunctionMiddleware
        if isinstance(middleware, FunctionMiddleware):
            self._middlewares.append(middleware)
        elif callable(middleware):
            self._middlewares.append(FunctionMiddlewareWrapper(middleware))

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

        def create_next_handler(index: int) -> Callable[[FunctionInvocationContext], Awaitable[None]]:
            if index >= len(self._middlewares):

                async def final_wrapper(c: FunctionInvocationContext) -> None:
                    result_container["result"] = await final_handler(c)

                return final_wrapper

            middleware = self._middlewares[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: FunctionInvocationContext) -> None:
                await middleware.process(c, next_handler)

            return current_handler

        first_handler = create_next_handler(0)
        await first_handler(context)

        # Return the result from result container
        return result_container["result"]

    @property
    def has_middlewares(self) -> bool:
        """Check if there are any middlewares registered."""
        return bool(self._middlewares)


# Decorator for adding middleware support to agent classes
def use_agent_middleware(agent_class: type[TAgent]) -> type[TAgent]:
    """Class decorator that adds middleware support to an agent class.

    This decorator adds middleware functionality to any agent class.
    It wraps the run() and run_stream() methods to provide middleware execution.

    Args:
        agent_class: The agent class to add middleware support to.

    Returns:
        The modified agent class with middleware support.
    """
    import inspect

    # Store original methods
    original_run = agent_class.run  # type: ignore[attr-defined]
    original_run_stream = agent_class.run_stream  # type: ignore[attr-defined]

    def _initialize_middleware_pipelines(self: Any, middlewares: MiddlewareType | list[MiddlewareType] | None) -> None:
        """Initialize agent and function middleware pipelines from the provided middleware list."""
        if not middlewares:
            return

        middleware_list: list[MiddlewareType] = middlewares if isinstance(middlewares, list) else [middlewares]  # type: ignore

        # Separate agent and function middleware using isinstance checks
        agent_middlewares: list[AgentMiddleware | AgentMiddlewareCallable] = []
        function_middlewares: list[FunctionMiddleware | FunctionMiddlewareCallable] = []

        for middleware in middleware_list:
            if isinstance(middleware, AgentMiddleware):
                agent_middlewares.append(middleware)
            elif isinstance(middleware, FunctionMiddleware):
                function_middlewares.append(middleware)
            elif callable(middleware):  # type: ignore[arg-type]
                # Check function signature to determine type
                try:
                    sig = inspect.signature(middleware)
                    params = list(sig.parameters.values())
                    if len(params) >= 1:
                        first_param = params[0]
                        # Check if first parameter is AgentInvocationContext or FunctionInvocationContext
                        if (
                            hasattr(first_param.annotation, "__name__")
                            and first_param.annotation.__name__ == "AgentInvocationContext"
                        ):
                            agent_middlewares.append(middleware)  # type: ignore
                        elif (
                            hasattr(first_param.annotation, "__name__")
                            and first_param.annotation.__name__ == "FunctionInvocationContext"
                        ):
                            function_middlewares.append(middleware)  # type: ignore
                        else:
                            # Default to agent middleware if uncertain
                            agent_middlewares.append(middleware)  # type: ignore
                    else:
                        agent_middlewares.append(middleware)  # type: ignore
                except Exception:
                    # If signature inspection fails, assume it's an agent middleware
                    agent_middlewares.append(middleware)  # type: ignore
            else:
                # Fallback
                agent_middlewares.append(middleware)  # type: ignore

        self._agent_middleware_pipeline = AgentMiddlewarePipeline(agent_middlewares)
        self._function_middleware_pipeline = FunctionMiddlewarePipeline(function_middlewares)

    async def middleware_enabled_run(
        self: Any,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Middleware-enabled run method."""
        # Initialize middleware pipelines if not already done
        if (
            hasattr(self, "middleware")
            and self.middleware
            and not (
                hasattr(self, "_agent_middleware_pipeline")
                and hasattr(self, "_function_middleware_pipeline")
                and (
                    self._agent_middleware_pipeline.has_middlewares
                    or self._function_middleware_pipeline.has_middlewares
                )
            )
        ):
            _initialize_middleware_pipelines(self, self.middleware)

        # Ensure pipelines exist even if empty
        if not hasattr(self, "_agent_middleware_pipeline"):
            self._agent_middleware_pipeline = AgentMiddlewarePipeline()
        if not hasattr(self, "_function_middleware_pipeline"):
            self._function_middleware_pipeline = FunctionMiddlewarePipeline()

        # Add function middleware pipeline to kwargs if available
        if self._function_middleware_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = self._function_middleware_pipeline

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if self._agent_middleware_pipeline.has_middlewares:
            context = AgentInvocationContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=False,
            )

            async def _execute_handler(ctx: AgentInvocationContext) -> AgentRunResponse:
                return await original_run(self, ctx.messages, thread=thread, **kwargs)  # type: ignore

            response = await self._agent_middleware_pipeline.execute(
                self,  # type: ignore[arg-type]
                normalized_messages,
                context,
                _execute_handler,
            )

            return response if response else AgentRunResponse()

        # No middleware, execute directly
        return await original_run(self, normalized_messages, thread=thread, **kwargs)  # type: ignore[return-value]

    def middleware_enabled_run_stream(
        self: Any,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Middleware-enabled run_stream method."""
        # Initialize middleware pipelines if not already done
        if (
            hasattr(self, "middleware")
            and self.middleware
            and not (
                hasattr(self, "_agent_middleware_pipeline")
                and hasattr(self, "_function_middleware_pipeline")
                and (
                    self._agent_middleware_pipeline.has_middlewares
                    or self._function_middleware_pipeline.has_middlewares
                )
            )
        ):
            _initialize_middleware_pipelines(self, self.middleware)

        # Ensure pipelines exist even if empty
        if not hasattr(self, "_agent_middleware_pipeline"):
            self._agent_middleware_pipeline = AgentMiddlewarePipeline()
        if not hasattr(self, "_function_middleware_pipeline"):
            self._function_middleware_pipeline = FunctionMiddlewarePipeline()

        # Add function middleware pipeline to kwargs if available
        if self._function_middleware_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = self._function_middleware_pipeline

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if self._agent_middleware_pipeline.has_middlewares:
            context = AgentInvocationContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=True,
            )

            async def _execute_stream_handler(ctx: AgentInvocationContext) -> AsyncIterable[AgentRunResponseUpdate]:
                async for update in original_run_stream(self, ctx.messages, thread=thread, **kwargs):  # type: ignore[misc]
                    yield update

            async def _stream_generator() -> AsyncIterable[AgentRunResponseUpdate]:
                async for update in self._agent_middleware_pipeline.execute_stream(
                    self,  # type: ignore[arg-type]
                    normalized_messages,
                    context,
                    _execute_stream_handler,
                ):
                    yield update

            return _stream_generator()

        # No middleware, execute directly
        return original_run_stream(self, normalized_messages, thread=thread, **kwargs)  # type: ignore

    agent_class.run = middleware_enabled_run  # type: ignore
    agent_class.run_stream = middleware_enabled_run_stream  # type: ignore

    return agent_class
