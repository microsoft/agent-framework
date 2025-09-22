# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

from ._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage

if TYPE_CHECKING:
    from pydantic import BaseModel

    from ._agents import AgentProtocol
    from ._tools import AIFunction

TAgent = TypeVar("TAgent", bound="AgentProtocol")


class MiddlewareType(Enum):
    """Enum representing the type of middleware."""

    AGENT = "agent"
    FUNCTION = "function"


__all__ = [
    "AgentMiddleware",
    "AgentRunContext",
    "FunctionInvocationContext",
    "FunctionMiddleware",
    "Middleware",
    "agent_middleware",
    "function_middleware",
    "use_agent_middleware",
]


@dataclass
class AgentRunContext:
    """Context object for agent middleware invocations.

    Attributes:
        agent: The agent being invoked.
        messages: The messages being sent to the agent.
        is_streaming: Whether this is a streaming invocation.
        metadata: Metadata dictionary for sharing data between agent middleware.
        result: Agent execution result. Can be observed after calling next()
                to see the actual execution result or can be set to override the execution result.
                For non-streaming: should be AgentRunResponse
                For streaming: should be AsyncIterable[AgentRunResponseUpdate]
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
    """

    agent: "AgentProtocol"
    messages: list[ChatMessage]
    is_streaming: bool = False
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    result: AgentRunResponse | AsyncIterable[AgentRunResponseUpdate] | None = None
    terminate: bool = False


@dataclass
class FunctionInvocationContext:
    """Context object for function middleware invocations.

    Attributes:
        function: The function being invoked.
        arguments: The validated arguments for the function.
        metadata: Metadata dictionary for sharing data between function middleware.
        result: Function execution result. Can be observed after calling next()
                to see the actual execution result or can be set to override the execution result.
        terminate: A flag indicating whether to terminate execution after current middleware.
                When set to True, execution will stop as soon as control returns to framework.
    """

    function: "AIFunction[Any, Any]"
    arguments: "BaseModel"
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    result: Any = None
    terminate: bool = False


class AgentMiddleware(ABC):
    """Abstract base class for agent middleware that can intercept agent invocations."""

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


# Pure function type definitions for convenience
AgentMiddlewareCallable = Callable[[AgentRunContext, Callable[[AgentRunContext], Awaitable[None]]], Awaitable[None]]

FunctionMiddlewareCallable = Callable[
    [FunctionInvocationContext, Callable[[FunctionInvocationContext], Awaitable[None]]], Awaitable[None]
]

# Type alias for all middleware types
Middleware: TypeAlias = AgentMiddleware | AgentMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable


# Middleware type markers for decorators
def agent_middleware(func: AgentMiddlewareCallable) -> AgentMiddlewareCallable:
    """Decorator to mark a function as agent middleware.

    This decorator explicitly identifies a function as agent middleware,
    which processes AgentRunContext objects.

    Args:
        func: The middleware function to mark as agent middleware.

    Returns:
        The same function with agent middleware marker.

    Example:
        @agent_middleware
        async def my_middleware(context: AgentRunContext, next):
            # Process agent invocation
            await next(context)
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

    Example:
        @function_middleware
        async def my_middleware(context: FunctionInvocationContext, next):
            # Process function invocation
            await next(context)
    """
    # Add marker attribute to identify this as function middleware
    func._middleware_type: MiddlewareType = MiddlewareType.FUNCTION  # type: ignore
    return func


class AgentMiddlewareWrapper(AgentMiddleware):
    """Wrapper to convert pure functions into AgentMiddleware protocol objects."""

    def __init__(self, func: AgentMiddlewareCallable):
        self.func = func

    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
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


class BaseMiddlewarePipeline(ABC):
    """Base class for middleware pipeline execution."""

    def __init__(self) -> None:
        """Initialize the base middleware pipeline."""
        self._middlewares: list[Any] = []

    @abstractmethod
    def _register_middleware(self, middleware: Any) -> None:
        """Register a middleware item. Must be implemented by subclasses."""
        ...

    @property
    def has_middlewares(self) -> bool:
        """Check if there are any middlewares registered."""
        return bool(self._middlewares)

    def _create_handler_chain(
        self,
        final_handler: Callable[[Any], Awaitable[Any]],
        result_container: dict[str, Any],
        result_key: str = "result",
    ) -> Callable[[Any], Awaitable[None]]:
        """Create a chain of middleware handlers.

        Args:
            final_handler: The final handler to execute
            result_container: Container to store the result
            result_key: Key to use in the result container

        Returns:
            The first handler in the chain
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


class AgentMiddlewarePipeline(BaseMiddlewarePipeline):
    """Executes agent middleware in a chain."""

    def __init__(self, middlewares: list[AgentMiddleware | AgentMiddlewareCallable] | None = None):
        """Initialize the agent middleware pipeline.

        Args:
            middlewares: List of agent middleware to include in the pipeline.
        """
        super().__init__()
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
        result_container: dict[str, AgentRunResponse | None] = {"response": None}

        def create_next_handler(index: int) -> Callable[[AgentRunContext], Awaitable[None]]:
            if index >= len(self._middlewares):

                async def final_wrapper(c: AgentRunContext) -> None:
                    # If terminate was set, skip execution
                    if c.terminate:
                        return

                    # Execute actual handler and populate context for observability
                    result = await final_handler(c)
                    result_container["result"] = result
                    c.result = result

                return final_wrapper

            middleware = self._middlewares[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: AgentRunContext) -> None:
                # If terminate is set, don't continue the pipeline
                if c.terminate:
                    return

                await middleware.process(c, next_handler)
                # After middleware execution, check if response was overridden
                if c.result is not None and isinstance(c.result, AgentRunResponse):
                    result_container["result"] = c.result

            return current_handler

        first_handler = create_next_handler(0)
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

        def create_next_handler(index: int) -> Callable[[AgentRunContext], Awaitable[None]]:
            if index >= len(self._middlewares):

                async def final_wrapper(c: AgentRunContext) -> None:  # noqa: RUF029
                    # If terminate was set, skip execution
                    if c.terminate:
                        return

                    # Execute actual handler and populate context for observability
                    result = final_handler(c)
                    result_container["result_stream"] = result
                    c.result = result

                return final_wrapper

            middleware = self._middlewares[index]
            next_handler = create_next_handler(index + 1)

            async def current_handler(c: AgentRunContext) -> None:
                await middleware.process(c, next_handler)
                # If terminate is set, don't continue the pipeline
                if c.terminate:
                    return

            return current_handler

        first_handler = create_next_handler(0)
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
    """Executes function middleware in a chain."""

    def __init__(self, middlewares: list[FunctionMiddleware | FunctionMiddlewareCallable] | None = None):
        """Initialize the function middleware pipeline.

        Args:
            middlewares: List of function middleware to include in the pipeline.
        """
        super().__init__()
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


# Decorator for adding middleware support to agent classes
def use_agent_middleware(agent_class: type[TAgent]) -> type[TAgent]:
    """Class decorator that adds middleware support to an agent class.

    This decorator adds middleware functionality to any agent class.
    It wraps the run() and run_stream() methods to provide middleware execution.

    The middleware execution can be terminated at any point by setting the
    context.terminate property to True. Once set, the pipeline will stop executing
    further middleware as soon as control returns to the pipeline.

    Args:
        agent_class: The agent class to add middleware support to.

    Returns:
        The modified agent class with middleware support.
    """
    import inspect

    # Store original methods
    original_run = agent_class.run  # type: ignore[attr-defined]
    original_run_stream = agent_class.run_stream  # type: ignore[attr-defined]

    def _determine_middleware_type(middleware: Any) -> MiddlewareType:
        """Determine middleware type using decorator and/or parameter type annotation.

        Args:
            middleware: The middleware function to analyze.

        Returns:
            MiddlewareType.AGENT or MiddlewareType.FUNCTION indicating the middleware type.

        Raises:
            ValueError: When middleware type cannot be determined or there's a mismatch.
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
            else:
                # Not enough parameters - can't be valid middleware
                raise ValueError(
                    f"Middleware function must have at least 2 parameters (context, next), "
                    f"but {middleware.__name__} has {len(params)}"
                )
        except Exception as e:
            if isinstance(e, ValueError):
                raise  # Re-raise our custom errors
            # Signature inspection failed - continue with other checks
            pass

        if decorator_type and param_type:
            # Both decorator and parameter type specified - they must match
            if decorator_type != param_type:
                raise ValueError(
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
        raise ValueError(
            f"Cannot determine middleware type for function {middleware.__name__}. "
            f"Please either use @agent_middleware/@function_middleware decorators "
            f"or specify parameter types (AgentRunContext or FunctionInvocationContext)."
        )

    def _build_middleware_pipelines(
        agent_level_middlewares: Middleware | list[Middleware] | None,
        run_level_middlewares: Middleware | list[Middleware] | None = None,
    ) -> tuple[AgentMiddlewarePipeline, FunctionMiddlewarePipeline]:
        """Build fresh agent and function middleware pipelines from the provided middleware lists.

        Args:
            agent_level_middlewares: Agent-level middleware (executed first)
            run_level_middlewares: Run-level middleware (executed after agent middleware)
        """
        # Merge middleware lists: agent middleware first, then run middleware
        combined_middlewares: list[Middleware] = []

        if agent_level_middlewares:
            if isinstance(agent_level_middlewares, list):
                combined_middlewares.extend(agent_level_middlewares)  # type: ignore[arg-type]
            else:
                combined_middlewares.append(agent_level_middlewares)

        if run_level_middlewares:
            if isinstance(run_level_middlewares, list):
                combined_middlewares.extend(run_level_middlewares)  # type: ignore[arg-type]
            else:
                combined_middlewares.append(run_level_middlewares)

        if not combined_middlewares:
            return AgentMiddlewarePipeline(), FunctionMiddlewarePipeline()

        middleware_list = combined_middlewares

        # Separate agent and function middleware using isinstance checks
        agent_middlewares: list[AgentMiddleware | AgentMiddlewareCallable] = []
        function_middlewares: list[FunctionMiddleware | FunctionMiddlewareCallable] = []

        for middleware in middleware_list:
            if isinstance(middleware, AgentMiddleware):
                agent_middlewares.append(middleware)
            elif isinstance(middleware, FunctionMiddleware):
                function_middlewares.append(middleware)
            elif callable(middleware):  # type: ignore[arg-type]
                # Determine middleware type using decorator and/or parameter type annotation
                middleware_type = _determine_middleware_type(middleware)
                if middleware_type == MiddlewareType.AGENT:
                    agent_middlewares.append(middleware)  # type: ignore
                elif middleware_type == MiddlewareType.FUNCTION:
                    function_middlewares.append(middleware)  # type: ignore
                else:
                    # This should not happen if _determine_middleware_type is implemented correctly
                    raise ValueError(f"Unknown middleware type: {middleware_type}")
            else:
                # Fallback
                agent_middlewares.append(middleware)  # type: ignore

        return AgentMiddlewarePipeline(agent_middlewares), FunctionMiddlewarePipeline(function_middlewares)

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
        agent_pipeline, function_pipeline = _build_middleware_pipelines(agent_middleware, middleware)

        # Add function middleware pipeline to kwargs if available
        if function_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = function_pipeline

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if agent_pipeline.has_middlewares:
            context = AgentRunContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=False,
            )

            async def _execute_handler(ctx: AgentRunContext) -> AgentRunResponse:
                return await original_run(self, ctx.messages, thread=thread, **kwargs)  # type: ignore

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
        agent_pipeline, function_pipeline = _build_middleware_pipelines(agent_middleware, middleware)

        # Add function middleware pipeline to kwargs if available
        if function_pipeline.has_middlewares:
            kwargs["_function_middleware_pipeline"] = function_pipeline

        normalized_messages = self._normalize_messages(messages)

        # Execute with middleware if available
        if agent_pipeline.has_middlewares:
            context = AgentRunContext(
                agent=self,  # type: ignore[arg-type]
                messages=normalized_messages,
                is_streaming=True,
            )

            async def _execute_stream_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
                async for update in original_run_stream(self, ctx.messages, thread=thread, **kwargs):  # type: ignore[misc]
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

    agent_class.run = middleware_enabled_run  # type: ignore
    agent_class.run_stream = middleware_enabled_run_stream  # type: ignore

    return agent_class
