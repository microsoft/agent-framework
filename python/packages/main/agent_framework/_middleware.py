# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pydantic import BaseModel

    from ._agents import AgentProtocol
    from ._tools import AIFunction
    from ._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage

__all__ = [
    "AgentInvocationContext",
    "AgentMiddleware",
    "FunctionInvocationContext",
    "FunctionMiddleware",
    "MiddlewareType",
]


class AgentInvocationContext:
    """Context object for agent middleware invocations.

    Attributes:
        agent: The agent being invoked.
        messages: The messages being sent to the agent.
        is_streaming: Whether this is a streaming invocation.
        request_id: Unique identifier for the current request.
        metadata: Metadata dictionary for sharing data between agent middleware.
    """

    def __init__(
        self,
        agent: "AgentProtocol",
        messages: list["ChatMessage"],
        is_streaming: bool = False,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize agent invocation context.

        Args:
            agent: The agent being invoked.
            messages: The messages being sent to the agent.
            is_streaming: Whether this is a streaming invocation.
            request_id: Unique identifier for the request. Auto-generated if None.
            metadata: Metadata dictionary.
        """
        self.agent = agent
        self.messages = messages
        self.is_streaming = is_streaming
        self.request_id = request_id or str(uuid4())
        self.metadata = metadata or {}


class FunctionInvocationContext:
    """Context object for function middleware invocations.

    Attributes:
        function: The function being invoked.
        arguments: The validated arguments for the function.
        request_id: Unique identifier for the current request.
        metadata: Metadata dictionary for sharing data between function middleware.
    """

    def __init__(
        self,
        function: "AIFunction[Any, Any]",
        arguments: "BaseModel",
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize function invocation context.

        Args:
            function: The function being invoked.
            arguments: The validated arguments for the function.
            request_id: Unique identifier for the request. Auto-generated if None.
            metadata: Metadata dictionary.
        """
        self.function = function
        self.arguments = arguments
        self.request_id = request_id or str(uuid4())
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


class AgentMiddlewareWrapper:
    """Wrapper to convert pure functions into AgentMiddleware protocol objects."""

    def __init__(self, func: AgentMiddlewareCallable):
        self.func = func

    async def process(
        self,
        context: AgentInvocationContext,
        next: Callable[[AgentInvocationContext], Awaitable[None]],
    ) -> None:
        await self.func(context, next)


class FunctionMiddlewareWrapper:
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
        if callable(middleware):
            # Check if it's already a protocol implementation
            if callable(middleware) and not hasattr(middleware, "func"):
                # It's a class instance implementing the protocol
                self._middlewares.append(middleware)  # type: ignore
            else:
                # It's a pure function, wrap it
                self._middlewares.append(AgentMiddlewareWrapper(middleware))  # type: ignore
        else:
            self._middlewares.append(middleware)  # type: ignore

    async def execute(
        self,
        agent: "AgentProtocol",
        messages: list["ChatMessage"],
        context: AgentInvocationContext,
        final_handler: Callable[[AgentInvocationContext], Awaitable["AgentRunResponse"]],
    ) -> "AgentRunResponse":
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
        response = result_container["response"]
        if response is None:
            raise RuntimeError("No response set after middleware execution")
        return response

    async def execute_stream(
        self,
        agent: "AgentProtocol",
        messages: list["ChatMessage"],
        context: AgentInvocationContext,
        final_handler: Callable[[AgentInvocationContext], AsyncIterable["AgentRunResponseUpdate"]],
    ) -> AsyncIterable["AgentRunResponseUpdate"]:
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
        if callable(middleware):
            # Check if it's already a protocol implementation
            if callable(middleware) and not hasattr(middleware, "func"):
                # It's a class instance implementing the protocol
                self._middlewares.append(middleware)  # type: ignore
            else:
                # It's a pure function, wrap it
                self._middlewares.append(FunctionMiddlewareWrapper(middleware))  # type: ignore
        else:
            self._middlewares.append(middleware)  # type: ignore

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
        result = result_container["result"]
        if result is None:
            raise RuntimeError("No result set after middleware execution")
        return result

    @property
    def has_middlewares(self) -> bool:
        """Check if there are any middlewares registered."""
        return bool(self._middlewares)
