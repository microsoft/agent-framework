# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable, MutableSequence
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
)
from agent_framework._clients import BaseChatClient
from agent_framework._middleware import (
    AgentMiddleware,
    AgentMiddlewarePipeline,
    AgentRunContext,
    FunctionInvocationContext,
    FunctionMiddleware,
    FunctionMiddlewarePipeline,
)
from agent_framework._tools import AIFunction, use_function_invocation
from agent_framework._types import ChatOptions


class TestAgentRunContext:
    """Test cases for AgentRunContext."""

    def test_init_with_defaults(self, mock_agent: AgentProtocol) -> None:
        """Test AgentRunContext initialization with default values."""
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        assert context.agent is mock_agent
        assert context.messages == messages
        assert context.is_streaming is False
        assert context.metadata == {}

    def test_init_with_custom_values(self, mock_agent: AgentProtocol) -> None:
        """Test AgentRunContext initialization with custom values."""
        messages = [ChatMessage(role=Role.USER, text="test")]
        metadata = {"key": "value"}
        context = AgentRunContext(agent=mock_agent, messages=messages, is_streaming=True, metadata=metadata)

        assert context.agent is mock_agent
        assert context.messages == messages
        assert context.is_streaming is True
        assert context.metadata == metadata


class TestFunctionInvocationContext:
    """Test cases for FunctionInvocationContext."""

    def test_init_with_defaults(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test FunctionInvocationContext initialization with default values."""
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        assert context.function is mock_function
        assert context.arguments == arguments
        assert context.metadata == {}

    def test_init_with_custom_metadata(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test FunctionInvocationContext initialization with custom metadata."""
        arguments = FunctionTestArgs(name="test")
        metadata = {"key": "value"}
        context = FunctionInvocationContext(function=mock_function, arguments=arguments, metadata=metadata)

        assert context.function is mock_function
        assert context.arguments == arguments
        assert context.metadata == metadata


class TestAgentMiddlewarePipeline:
    """Test cases for AgentMiddlewarePipeline."""

    def test_init_empty(self) -> None:
        """Test AgentMiddlewarePipeline initialization with no middlewares."""
        pipeline = AgentMiddlewarePipeline()
        assert not pipeline.has_middlewares

    def test_init_with_class_middleware(self) -> None:
        """Test AgentMiddlewarePipeline initialization with class-based middleware."""
        middleware = TestAgentMiddleware()
        pipeline = AgentMiddlewarePipeline([middleware])
        assert pipeline.has_middlewares

    def test_init_with_function_middleware(self) -> None:
        """Test AgentMiddlewarePipeline initialization with function-based middleware."""

        async def test_middleware(context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]) -> None:
            await next(context)

        pipeline = AgentMiddlewarePipeline([test_middleware])
        assert pipeline.has_middlewares

    async def test_execute_no_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test pipeline execution with no middleware."""
        pipeline = AgentMiddlewarePipeline()
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        expected_response = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            return expected_response

        result = await pipeline.execute(mock_agent, messages, context, final_handler)
        assert result == expected_response

    async def test_execute_with_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test pipeline execution with middleware."""
        execution_order: list[str] = []

        class OrderTrackingMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        middleware = OrderTrackingMiddleware("test")
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        expected_response = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            execution_order.append("handler")
            return expected_response

        result = await pipeline.execute(mock_agent, messages, context, final_handler)
        assert result == expected_response
        assert execution_order == ["test_before", "handler", "test_after"]

    async def test_execute_stream_no_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test pipeline streaming execution with no middleware."""
        pipeline = AgentMiddlewarePipeline()
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk1")])
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk2")])

        updates: list[AgentRunResponseUpdate] = []
        async for update in pipeline.execute_stream(mock_agent, messages, context, final_handler):
            updates.append(update)

        assert len(updates) == 2
        assert updates[0].text == "chunk1"
        assert updates[1].text == "chunk2"

    async def test_execute_stream_with_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test pipeline streaming execution with middleware."""
        execution_order: list[str] = []

        class StreamOrderTrackingMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        middleware = StreamOrderTrackingMiddleware("test")
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
            execution_order.append("handler_start")
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk1")])
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk2")])
            execution_order.append("handler_end")

        updates: list[AgentRunResponseUpdate] = []
        async for update in pipeline.execute_stream(mock_agent, messages, context, final_handler):
            updates.append(update)

        assert len(updates) == 2
        assert updates[0].text == "chunk1"
        assert updates[1].text == "chunk2"
        assert execution_order == ["test_before", "test_after", "handler_start", "handler_end"]


class TestFunctionMiddlewarePipeline:
    """Test cases for FunctionMiddlewarePipeline."""

    def test_init_empty(self) -> None:
        """Test FunctionMiddlewarePipeline initialization with no middlewares."""
        pipeline = FunctionMiddlewarePipeline()
        assert not pipeline.has_middlewares

    def test_init_with_class_middleware(self) -> None:
        """Test FunctionMiddlewarePipeline initialization with class-based middleware."""
        middleware = TestFunctionMiddleware()
        pipeline = FunctionMiddlewarePipeline([middleware])
        assert pipeline.has_middlewares

    def test_init_with_function_middleware(self) -> None:
        """Test FunctionMiddlewarePipeline initialization with function-based middleware."""

        async def test_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            await next(context)

        pipeline = FunctionMiddlewarePipeline([test_middleware])
        assert pipeline.has_middlewares

    async def test_execute_no_middleware(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test pipeline execution with no middleware."""
        pipeline = FunctionMiddlewarePipeline()
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        expected_result = "function_result"

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            return expected_result

        result = await pipeline.execute(mock_function, arguments, context, final_handler)
        assert result == expected_result

    async def test_execute_with_middleware(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test pipeline execution with middleware."""
        execution_order: list[str] = []

        class OrderTrackingFunctionMiddleware(FunctionMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        middleware = OrderTrackingFunctionMiddleware("test")
        pipeline = FunctionMiddlewarePipeline([middleware])
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        expected_result = "function_result"

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            execution_order.append("handler")
            return expected_result

        result = await pipeline.execute(mock_function, arguments, context, final_handler)
        assert result == expected_result
        assert execution_order == ["test_before", "handler", "test_after"]


class TestClassBasedMiddleware:
    """Test cases for class-based middleware implementations."""

    async def test_agent_middleware_execution(self, mock_agent: AgentProtocol) -> None:
        """Test class-based agent middleware execution."""
        metadata_updates: list[str] = []

        class MetadataAgentMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                context.metadata["before"] = True
                metadata_updates.append("before")
                await next(context)
                context.metadata["after"] = True
                metadata_updates.append("after")

        middleware = MetadataAgentMiddleware()
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            metadata_updates.append("handler")
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        result = await pipeline.execute(mock_agent, messages, context, final_handler)

        assert result is not None
        assert context.metadata["before"] is True
        assert context.metadata["after"] is True
        assert metadata_updates == ["before", "handler", "after"]

    async def test_function_middleware_execution(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test class-based function middleware execution."""
        metadata_updates: list[str] = []

        class MetadataFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                context.metadata["before"] = True
                metadata_updates.append("before")
                await next(context)
                context.metadata["after"] = True
                metadata_updates.append("after")

        middleware = MetadataFunctionMiddleware()
        pipeline = FunctionMiddlewarePipeline([middleware])
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            metadata_updates.append("handler")
            return "result"

        result = await pipeline.execute(mock_function, arguments, context, final_handler)

        assert result == "result"
        assert context.metadata["before"] is True
        assert context.metadata["after"] is True
        assert metadata_updates == ["before", "handler", "after"]


class TestFunctionBasedMiddleware:
    """Test cases for function-based middleware implementations."""

    async def test_agent_function_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test function-based agent middleware."""
        execution_order: list[str] = []

        async def test_agent_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_before")
            context.metadata["function_middleware"] = True
            await next(context)
            execution_order.append("function_after")

        pipeline = AgentMiddlewarePipeline([test_agent_middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            execution_order.append("handler")
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        result = await pipeline.execute(mock_agent, messages, context, final_handler)

        assert result is not None
        assert context.metadata["function_middleware"] is True
        assert execution_order == ["function_before", "handler", "function_after"]

    async def test_function_function_middleware(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test function-based function middleware."""
        execution_order: list[str] = []

        async def test_function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_before")
            context.metadata["function_middleware"] = True
            await next(context)
            execution_order.append("function_after")

        pipeline = FunctionMiddlewarePipeline([test_function_middleware])
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            execution_order.append("handler")
            return "result"

        result = await pipeline.execute(mock_function, arguments, context, final_handler)

        assert result == "result"
        assert context.metadata["function_middleware"] is True
        assert execution_order == ["function_before", "handler", "function_after"]


class TestMixedMiddleware:
    """Test cases for mixed class and function-based middleware."""

    async def test_mixed_agent_middleware(self, mock_agent: AgentProtocol) -> None:
        """Test mixed class and function-based agent middleware."""
        execution_order: list[str] = []

        class ClassMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("class_before")
                await next(context)
                execution_order.append("class_after")

        async def function_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_before")
            await next(context)
            execution_order.append("function_after")

        pipeline = AgentMiddlewarePipeline([ClassMiddleware(), function_middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            execution_order.append("handler")
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        result = await pipeline.execute(mock_agent, messages, context, final_handler)

        assert result is not None
        assert execution_order == ["class_before", "function_before", "handler", "function_after", "class_after"]

    async def test_mixed_function_middleware(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test mixed class and function-based function middleware."""
        execution_order: list[str] = []

        class ClassMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append("class_before")
                await next(context)
                execution_order.append("class_after")

        async def function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_before")
            await next(context)
            execution_order.append("function_after")

        pipeline = FunctionMiddlewarePipeline([ClassMiddleware(), function_middleware])
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            execution_order.append("handler")
            return "result"

        result = await pipeline.execute(mock_function, arguments, context, final_handler)

        assert result == "result"
        assert execution_order == ["class_before", "function_before", "handler", "function_after", "class_after"]


class TestMultipleMiddlewareOrdering:
    """Test cases for multiple middleware execution order."""

    async def test_agent_middleware_execution_order(self, mock_agent: AgentProtocol) -> None:
        """Test that multiple agent middlewares execute in registration order."""
        execution_order: list[str] = []

        class FirstMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("first_before")
                await next(context)
                execution_order.append("first_after")

        class SecondMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("second_before")
                await next(context)
                execution_order.append("second_after")

        class ThirdMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("third_before")
                await next(context)
                execution_order.append("third_after")

        middlewares = [FirstMiddleware(), SecondMiddleware(), ThirdMiddleware()]
        pipeline = AgentMiddlewarePipeline(middlewares)  # type: ignore
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            execution_order.append("handler")
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        result = await pipeline.execute(mock_agent, messages, context, final_handler)

        assert result is not None
        expected_order = [
            "first_before",
            "second_before",
            "third_before",
            "handler",
            "third_after",
            "second_after",
            "first_after",
        ]
        assert execution_order == expected_order

    async def test_function_middleware_execution_order(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test that multiple function middlewares execute in registration order."""
        execution_order: list[str] = []

        class FirstMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append("first_before")
                await next(context)
                execution_order.append("first_after")

        class SecondMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append("second_before")
                await next(context)
                execution_order.append("second_after")

        middlewares = [FirstMiddleware(), SecondMiddleware()]
        pipeline = FunctionMiddlewarePipeline(middlewares)  # type: ignore
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            execution_order.append("handler")
            return "result"

        result = await pipeline.execute(mock_function, arguments, context, final_handler)

        assert result == "result"
        expected_order = ["first_before", "second_before", "handler", "second_after", "first_after"]
        assert execution_order == expected_order


class TestContextContentValidation:
    """Test cases for validating middleware context content."""

    async def test_agent_context_validation(self, mock_agent: AgentProtocol) -> None:
        """Test that agent context contains expected data."""

        class ContextValidationMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                # Verify context has all expected attributes
                assert hasattr(context, "agent")
                assert hasattr(context, "messages")
                assert hasattr(context, "is_streaming")
                assert hasattr(context, "metadata")

                # Verify context content
                assert context.agent is mock_agent
                assert len(context.messages) == 1
                assert context.messages[0].role == Role.USER
                assert context.messages[0].text == "test"
                assert context.is_streaming is False
                assert isinstance(context.metadata, dict)

                # Add custom metadata
                context.metadata["validated"] = True

                await next(context)

        middleware = ContextValidationMiddleware()
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            # Verify metadata was set by middleware
            assert ctx.metadata.get("validated") is True
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        result = await pipeline.execute(mock_agent, messages, context, final_handler)
        assert result is not None

    async def test_function_context_validation(self, mock_function: AIFunction[Any, Any]) -> None:
        """Test that function context contains expected data."""

        class ContextValidationMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                # Verify context has all expected attributes
                assert hasattr(context, "function")
                assert hasattr(context, "arguments")
                assert hasattr(context, "metadata")

                # Verify context content
                assert context.function is mock_function
                assert isinstance(context.arguments, FunctionTestArgs)
                assert context.arguments.name == "test"
                assert isinstance(context.metadata, dict)

                # Add custom metadata
                context.metadata["validated"] = True

                await next(context)

        middleware = ContextValidationMiddleware()
        pipeline = FunctionMiddlewarePipeline([middleware])
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            # Verify metadata was set by middleware
            assert ctx.metadata.get("validated") is True
            return "result"

        result = await pipeline.execute(mock_function, arguments, context, final_handler)
        assert result == "result"


class TestStreamingScenarios:
    """Test cases for streaming and non-streaming scenarios."""

    async def test_streaming_flag_validation(self, mock_agent: AgentProtocol) -> None:
        """Test that is_streaming flag is correctly set for streaming calls."""
        streaming_flags: list[bool] = []

        class StreamingFlagMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                streaming_flags.append(context.is_streaming)
                await next(context)

        middleware = StreamingFlagMiddleware()
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]

        # Test non-streaming
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_handler(ctx: AgentRunContext) -> AgentRunResponse:
            streaming_flags.append(ctx.is_streaming)
            return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        await pipeline.execute(mock_agent, messages, context, final_handler)

        # Test streaming
        context_stream = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_stream_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
            streaming_flags.append(ctx.is_streaming)
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk")])

        updates: list[AgentRunResponseUpdate] = []
        async for update in pipeline.execute_stream(mock_agent, messages, context_stream, final_stream_handler):
            updates.append(update)

        # Verify flags: [non-streaming middleware, non-streaming handler, streaming middleware, streaming handler]
        assert streaming_flags == [False, False, True, True]

    async def test_streaming_middleware_behavior(self, mock_agent: AgentProtocol) -> None:
        """Test middleware behavior with streaming responses."""
        chunks_processed: list[str] = []

        class StreamProcessingMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                chunks_processed.append("before_stream")
                await next(context)
                chunks_processed.append("after_stream")

        middleware = StreamProcessingMiddleware()
        pipeline = AgentMiddlewarePipeline([middleware])
        messages = [ChatMessage(role=Role.USER, text="test")]
        context = AgentRunContext(agent=mock_agent, messages=messages)

        async def final_stream_handler(ctx: AgentRunContext) -> AsyncIterable[AgentRunResponseUpdate]:
            chunks_processed.append("stream_start")
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk1")])
            chunks_processed.append("chunk1_yielded")
            yield AgentRunResponseUpdate(contents=[TextContent(text="chunk2")])
            chunks_processed.append("chunk2_yielded")
            chunks_processed.append("stream_end")

        updates: list[str] = []
        async for update in pipeline.execute_stream(mock_agent, messages, context, final_stream_handler):
            updates.append(update.text)

        assert updates == ["chunk1", "chunk2"]
        assert chunks_processed == [
            "before_stream",
            "after_stream",
            "stream_start",
            "chunk1_yielded",
            "chunk2_yielded",
            "stream_end",
        ]


# region Helper classes and fixtures


class FunctionTestArgs(BaseModel):
    """Test arguments for function middleware tests."""

    name: str = Field(description="Test name parameter")


class TestAgentMiddleware(AgentMiddleware):
    """Test implementation of AgentMiddleware."""

    async def process(self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]) -> None:
        await next(context)


class TestFunctionMiddleware(FunctionMiddleware):
    """Test implementation of FunctionMiddleware."""

    async def process(
        self, context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
    ) -> None:
        await next(context)


class MockFunctionArgs(BaseModel):
    """Test arguments for function middleware tests."""

    name: str = Field(description="Test name parameter")


@pytest.fixture
def mock_agent() -> AgentProtocol:
    """Mock agent for testing."""
    agent = MagicMock(spec=AgentProtocol)
    agent.name = "test_agent"
    return agent


@pytest.fixture
def mock_function() -> AIFunction[Any, Any]:
    """Mock function for testing."""
    function = MagicMock(spec=AIFunction[Any, Any])
    function.name = "test_function"
    return function


@use_function_invocation
class MockChatClient(BaseChatClient):
    """Mock chat client for ChatAgent integration tests."""

    call_count: int = Field(default=0)
    responses: list[ChatResponse] = Field(default_factory=lambda: [])
    streaming_responses: list[list[ChatResponseUpdate]] = Field(default_factory=lambda: [])

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Return a mock response."""
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Mock response")])

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Return mock streaming responses."""
        self.call_count += 1
        if self.streaming_responses:
            for update in self.streaming_responses.pop(0):
                yield update
        else:
            yield ChatResponseUpdate(contents=[TextContent(text="Mock")], role=Role.ASSISTANT)
            yield ChatResponseUpdate(contents=[TextContent(text=" streaming response")], role=Role.ASSISTANT)

    def service_url(self) -> str:
        return "https://mock.example.com"


@pytest.fixture
def mock_chat_client() -> MockChatClient:
    """Mock chat client fixture."""
    return MockChatClient()


# region ChatAgent Tests


class TestChatAgentClassBasedMiddleware:
    """Test cases for class-based middleware integration with ChatAgent."""

    async def test_class_based_agent_middleware_with_chat_agent(self, mock_chat_client: MockChatClient) -> None:
        """Test class-based agent middleware with ChatAgent."""
        execution_order: list[str] = []

        class TrackingAgentMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        # Create ChatAgent with middleware
        middleware = TrackingAgentMiddleware("agent_middleware")
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == Role.ASSISTANT
        assert response.messages[0].text == "Mock response"
        assert mock_chat_client.call_count == 1

        # Verify middleware execution order
        assert execution_order == ["agent_middleware_before", "agent_middleware_after"]

    async def test_class_based_function_middleware_with_chat_agent(self, mock_chat_client: MockChatClient) -> None:
        """Test class-based function middleware with ChatAgent."""
        execution_order: list[str] = []

        class TrackingFunctionMiddleware(FunctionMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        # Create ChatAgent with function middleware (no tools, so function middleware won't be triggered)
        middleware = TrackingFunctionMiddleware("function_middleware")
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert mock_chat_client.call_count == 1

        # Note: Function middleware won't execute since no function calls are made
        assert execution_order == []


class TestChatAgentFunctionBasedMiddleware:
    """Test cases for function-based middleware integration with ChatAgent."""

    async def test_function_based_agent_middleware_with_chat_agent(self, mock_chat_client: MockChatClient) -> None:
        """Test function-based agent middleware with ChatAgent."""
        execution_order: list[str] = []

        async def tracking_agent_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            execution_order.append("agent_function_before")
            await next(context)
            execution_order.append("agent_function_after")

        # Create ChatAgent with function middleware
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[tracking_agent_middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == Role.ASSISTANT
        assert response.messages[0].text == "Mock response"
        assert mock_chat_client.call_count == 1

        # Verify middleware execution order
        assert execution_order == ["agent_function_before", "agent_function_after"]

    async def test_function_based_function_middleware_with_chat_agent(self, mock_chat_client: MockChatClient) -> None:
        """Test function-based function middleware with ChatAgent."""
        execution_order: list[str] = []

        async def tracking_function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await next(context)
            execution_order.append("function_function_after")

        # Create ChatAgent with function middleware (no tools, so function middleware won't be triggered)
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[tracking_function_middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert mock_chat_client.call_count == 1

        # Note: Function middleware won't execute since no function calls are made
        assert execution_order == []


class TestChatAgentStreamingMiddleware:
    """Test cases for streaming middleware integration with ChatAgent."""

    async def test_agent_middleware_with_streaming(self, mock_chat_client: MockChatClient) -> None:
        """Test agent middleware with streaming ChatAgent responses."""
        execution_order: list[str] = []
        streaming_flags: list[bool] = []

        class StreamingTrackingMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("middleware_before")
                streaming_flags.append(context.is_streaming)
                await next(context)
                execution_order.append("middleware_after")

        # Create ChatAgent with middleware
        middleware = StreamingTrackingMiddleware()
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[middleware])

        # Set up mock streaming responses
        mock_chat_client.streaming_responses = [
            [
                ChatResponseUpdate(contents=[TextContent(text="Streaming")], role=Role.ASSISTANT),
                ChatResponseUpdate(contents=[TextContent(text=" response")], role=Role.ASSISTANT),
            ]
        ]

        # Execute streaming
        messages = [ChatMessage(role=Role.USER, text="test message")]
        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream(messages):
            updates.append(update)

        # Verify streaming response
        assert len(updates) == 2
        assert updates[0].text == "Streaming"
        assert updates[1].text == " response"
        assert mock_chat_client.call_count == 1

        # Verify middleware was called and streaming flag was set correctly
        assert execution_order == ["middleware_before", "middleware_after"]
        assert streaming_flags == [True]  # Context should indicate streaming

    async def test_non_streaming_vs_streaming_flag_validation(self, mock_chat_client: MockChatClient) -> None:
        """Test that is_streaming flag is correctly set for different execution modes."""
        streaming_flags: list[bool] = []

        class FlagTrackingMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                streaming_flags.append(context.is_streaming)
                await next(context)

        # Create ChatAgent with middleware
        middleware = FlagTrackingMiddleware()
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[middleware])
        messages = [ChatMessage(role=Role.USER, text="test message")]

        # Test non-streaming execution
        response = await agent.run(messages)
        assert response is not None

        # Test streaming execution
        async for _ in agent.run_stream(messages):
            pass

        # Verify flags: [non-streaming, streaming]
        assert streaming_flags == [False, True]


class TestChatAgentMultipleMiddlewareOrdering:
    """Test cases for multiple middleware execution order with ChatAgent."""

    async def test_multiple_agent_middleware_execution_order(self, mock_chat_client: MockChatClient) -> None:
        """Test that multiple agent middlewares execute in correct order with ChatAgent."""
        execution_order: list[str] = []

        class OrderedMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        # Create multiple middlewares
        middleware1 = OrderedMiddleware("first")
        middleware2 = OrderedMiddleware("second")
        middleware3 = OrderedMiddleware("third")

        # Create ChatAgent with multiple middlewares
        agent = ChatAgent(chat_client=mock_chat_client, middleware=[middleware1, middleware2, middleware3])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert mock_chat_client.call_count == 1

        # Verify execution order (should be nested: first wraps second wraps third)
        expected_order = ["first_before", "second_before", "third_before", "third_after", "second_after", "first_after"]
        assert execution_order == expected_order

    async def test_mixed_middleware_types_with_chat_agent(self, mock_chat_client: MockChatClient) -> None:
        """Test mixed class and function-based middlewares with ChatAgent."""
        execution_order: list[str] = []

        class ClassAgentMiddleware(AgentMiddleware):
            async def process(
                self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
            ) -> None:
                execution_order.append("class_agent_before")
                await next(context)
                execution_order.append("class_agent_after")

        async def function_agent_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_agent_before")
            await next(context)
            execution_order.append("function_agent_after")

        class ClassFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append("class_function_before")
                await next(context)
                execution_order.append("class_function_after")

        async def function_function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await next(context)
            execution_order.append("function_function_after")

        # Create ChatAgent with mixed middleware types (no tools, focusing on agent middleware)
        agent = ChatAgent(
            chat_client=mock_chat_client,
            middleware=[
                ClassAgentMiddleware(),
                function_agent_middleware,
                ClassFunctionMiddleware(),  # Won't execute without function calls
                function_function_middleware,  # Won't execute without function calls
            ],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert mock_chat_client.call_count == 1

        # Verify that agent middlewares were executed in correct order
        # (Function middlewares won't execute since no functions are called)
        expected_order = ["class_agent_before", "function_agent_before", "function_agent_after", "class_agent_after"]
        assert execution_order == expected_order


# region Tool Functions for Testing


def sample_tool_function(location: str) -> str:
    """A simple tool function for middleware testing."""
    return f"Weather in {location}: sunny"


# region ChatAgent Function Middleware Tests with Tools


class TestChatAgentFunctionMiddlewareWithTools:
    """Test cases for function middleware integration with ChatAgent when tools are used."""

    async def test_class_based_function_middleware_with_tool_calls(self, mock_chat_client: MockChatClient) -> None:
        """Test class-based function middleware with ChatAgent when function calls are made."""
        execution_order: list[str] = []

        class TrackingFunctionMiddleware(FunctionMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await next(context)
                execution_order.append(f"{self.name}_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[
                        FunctionCallContent(
                            call_id="call_123",
                            name="sample_tool_function",
                            arguments='{"location": "Seattle"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Final response")])

        mock_chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with function middleware and tools
        middleware = TrackingFunctionMiddleware("function_middleware")
        agent = ChatAgent(
            chat_client=mock_chat_client,
            middleware=[middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for Seattle")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert mock_chat_client.call_count == 2  # Two calls: one for function call, one for final response

        # Verify function middleware was executed
        assert execution_order == ["function_middleware_before", "function_middleware_after"]

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if isinstance(c, FunctionCallContent)]
        function_results = [c for c in all_contents if isinstance(c, FunctionResultContent)]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id

    async def test_function_based_function_middleware_with_tool_calls(self, mock_chat_client: MockChatClient) -> None:
        """Test function-based function middleware with ChatAgent when function calls are made."""
        execution_order: list[str] = []

        async def tracking_function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_middleware_before")
            await next(context)
            execution_order.append("function_middleware_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[
                        FunctionCallContent(
                            call_id="call_456",
                            name="sample_tool_function",
                            arguments='{"location": "San Francisco"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Final response")])

        mock_chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with function middleware and tools
        agent = ChatAgent(
            chat_client=mock_chat_client,
            middleware=[tracking_function_middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for San Francisco")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert mock_chat_client.call_count == 2  # Two calls: one for function call, one for final response

        # Verify function middleware was executed
        assert execution_order == ["function_middleware_before", "function_middleware_after"]

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if isinstance(c, FunctionCallContent)]
        function_results = [c for c in all_contents if isinstance(c, FunctionResultContent)]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id

    async def test_mixed_agent_and_function_middleware_with_tool_calls(self, mock_chat_client: MockChatClient) -> None:
        """Test both agent and function middleware with ChatAgent when function calls are made."""
        execution_order: list[str] = []

        class TrackingAgentMiddleware(AgentMiddleware):
            async def process(
                self,
                context: AgentRunContext,
                next: Callable[[AgentRunContext], Awaitable[None]],
            ) -> None:
                execution_order.append("agent_middleware_before")
                await next(context)
                execution_order.append("agent_middleware_after")

        class TrackingFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                next: Callable[[FunctionInvocationContext], Awaitable[None]],
            ) -> None:
                execution_order.append("function_middleware_before")
                await next(context)
                execution_order.append("function_middleware_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[
                        FunctionCallContent(
                            call_id="call_789",
                            name="sample_tool_function",
                            arguments='{"location": "New York"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Final response")])

        mock_chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with both agent and function middleware and tools
        agent = ChatAgent(
            chat_client=mock_chat_client,
            middleware=[TrackingAgentMiddleware(), TrackingFunctionMiddleware()],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for New York")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert mock_chat_client.call_count == 2  # Two calls: one for function call, one for final response

        # Verify middleware execution order: agent middleware wraps everything,
        # function middleware only for function calls
        expected_order = [
            "agent_middleware_before",
            "function_middleware_before",
            "function_middleware_after",
            "agent_middleware_after",
        ]
        assert execution_order == expected_order

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if isinstance(c, FunctionCallContent)]
        function_results = [c for c in all_contents if isinstance(c, FunctionResultContent)]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id
