# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    ResponseStream,
    SupportsAgentRun,
)
from agent_framework._middleware import (
    AgentContext,
    AgentMiddleware,
    AgentMiddlewarePipeline,
    FunctionInvocationContext,
    FunctionMiddleware,
    FunctionMiddlewarePipeline,
)
from agent_framework._tools import FunctionTool

from .conftest import MockChatClient


class FunctionTestArgs(BaseModel):
    """Test arguments for function middleware tests."""

    name: str = Field(description="Test name parameter")


class TestResultOverrideMiddleware:
    """Test cases for middleware result override functionality."""

    async def test_agent_middleware_response_override_non_streaming(self, mock_agent: SupportsAgentRun) -> None:
        """Test that agent middleware can override response for non-streaming execution."""
        override_response = AgentResponse(messages=[Message(role="assistant", text="overridden response")])

        class ResponseOverrideMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Execute the pipeline first, then override the response
                await call_next()
                context.result = override_response

        middleware = ResponseOverrideMiddleware()
        pipeline = AgentMiddlewarePipeline(middleware)
        messages = [Message(role="user", text="test")]
        context = AgentContext(agent=mock_agent, messages=messages)

        handler_called = False

        async def final_handler(ctx: AgentContext) -> AgentResponse:
            nonlocal handler_called
            handler_called = True
            return AgentResponse(messages=[Message(role="assistant", text="original response")])

        result = await pipeline.execute(context, final_handler)

        # Verify the overridden response is returned
        assert result is not None
        assert result == override_response
        assert result.messages[0].text == "overridden response"
        # Verify original handler was called since middleware called next()
        assert handler_called

    async def test_agent_middleware_response_override_streaming(self, mock_agent: SupportsAgentRun) -> None:
        """Test that agent middleware can override response for streaming execution."""

        async def override_stream() -> AsyncIterable[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="overridden")])
            yield AgentResponseUpdate(contents=[Content.from_text(text=" stream")])

        class StreamResponseOverrideMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Execute the pipeline first, then override the response stream
                await call_next()
                context.result = ResponseStream(override_stream())

        middleware = StreamResponseOverrideMiddleware()
        pipeline = AgentMiddlewarePipeline(middleware)
        messages = [Message(role="user", text="test")]
        context = AgentContext(agent=mock_agent, messages=messages, stream=True)

        async def final_handler(ctx: AgentContext) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text="original")])

            return ResponseStream(_stream())

        updates: list[AgentResponseUpdate] = []
        stream = await pipeline.execute(context, final_handler)
        async for update in stream:
            updates.append(update)

        # Verify the overridden response stream is returned
        assert len(updates) == 2
        assert updates[0].text == "overridden"
        assert updates[1].text == " stream"

    async def test_function_middleware_result_override(self, mock_function: FunctionTool) -> None:
        """Test that function middleware can override result."""
        override_result = "overridden function result"

        class ResultOverrideMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                # Execute the pipeline first, then override the result
                await call_next()
                context.result = override_result

        middleware = ResultOverrideMiddleware()
        pipeline = FunctionMiddlewarePipeline(middleware)
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        handler_called = False

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            nonlocal handler_called
            handler_called = True
            return "original function result"

        result = await pipeline.execute(context, final_handler)

        # Verify the overridden result is returned
        assert result == override_result
        # Verify original handler was called since middleware called next()
        assert handler_called

    async def test_chat_agent_middleware_response_override(self) -> None:
        """Test result override functionality with Agent integration."""
        mock_chat_client = MockChatClient()

        class ChatAgentResponseOverrideMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Always call next() first to allow execution
                await call_next()
                # Then conditionally override based on content
                if any("special" in msg.text for msg in context.messages if msg.text):
                    context.result = AgentResponse(
                        messages=[Message(role="assistant", text="Special response from middleware!")]
                    )

        # Create Agent with override middleware
        middleware = ChatAgentResponseOverrideMiddleware()
        agent = Agent(client=mock_chat_client, middleware=[middleware])

        # Test override case
        override_messages = [Message(role="user", text="Give me a special response")]
        override_response = await agent.run(override_messages)
        assert override_response.messages[0].text == "Special response from middleware!"
        # Verify chat client was called since middleware called next()
        assert mock_chat_client.call_count == 1

        # Test normal case
        normal_messages = [Message(role="user", text="Normal request")]
        normal_response = await agent.run(normal_messages)
        assert normal_response.messages[0].text == "test response"
        # Verify chat client was called for normal case
        assert mock_chat_client.call_count == 2

    async def test_chat_agent_middleware_streaming_override(self) -> None:
        """Test streaming result override functionality with Agent integration."""
        mock_chat_client = MockChatClient()

        async def custom_stream() -> AsyncIterable[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="Custom")])
            yield AgentResponseUpdate(contents=[Content.from_text(text=" streaming")])
            yield AgentResponseUpdate(contents=[Content.from_text(text=" response!")])

        class ChatAgentStreamOverrideMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Check if we want to override BEFORE calling next to avoid creating unused streams
                if any("custom stream" in msg.text for msg in context.messages if msg.text):
                    context.result = ResponseStream(custom_stream())
                    return  # Don't call next() - we're overriding the entire result
                # Normal case - let the agent handle it
                await call_next()

        # Create Agent with override middleware
        middleware = ChatAgentStreamOverrideMiddleware()
        agent = Agent(client=mock_chat_client, middleware=[middleware])

        # Test streaming override case
        override_messages = [Message(role="user", text="Give me a custom stream")]
        override_updates: list[AgentResponseUpdate] = []
        async for update in agent.run(override_messages, stream=True):
            override_updates.append(update)

        assert len(override_updates) == 3
        assert override_updates[0].text == "Custom"
        assert override_updates[1].text == " streaming"
        assert override_updates[2].text == " response!"

        # Test normal streaming case
        normal_messages = [Message(role="user", text="Normal streaming request")]
        normal_updates: list[AgentResponseUpdate] = []
        async for update in agent.run(normal_messages, stream=True):
            normal_updates.append(update)

        assert len(normal_updates) == 2
        assert normal_updates[0].text == "test streaming response "
        assert normal_updates[1].text == "another update"

    async def test_agent_middleware_conditional_no_next(self, mock_agent: SupportsAgentRun) -> None:
        """Test that when agent middleware conditionally doesn't call next(), no execution happens."""

        class ConditionalNoNextMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Only call next() if message contains "execute"
                if any("execute" in msg.text for msg in context.messages if msg.text):
                    await call_next()
                # Otherwise, don't call next() - no execution should happen

        middleware = ConditionalNoNextMiddleware()
        pipeline = AgentMiddlewarePipeline(middleware)

        handler_called = False

        async def final_handler(ctx: AgentContext) -> AgentResponse:
            nonlocal handler_called
            handler_called = True
            return AgentResponse(messages=[Message(role="assistant", text="executed response")])

        # Test case where next() is NOT called
        no_execute_messages = [Message(role="user", text="Don't run this")]
        no_execute_context = AgentContext(agent=mock_agent, messages=no_execute_messages, stream=False)
        no_execute_result = await pipeline.execute(no_execute_context, final_handler)

        # When middleware doesn't call next(), result should be empty AgentResponse
        assert no_execute_result is None
        assert not handler_called

        # Reset for next test
        handler_called = False

        # Test case where next() IS called
        execute_messages = [Message(role="user", text="Please execute this")]
        execute_context = AgentContext(agent=mock_agent, messages=execute_messages, stream=False)
        execute_result = await pipeline.execute(execute_context, final_handler)

        assert execute_result is not None
        assert execute_result.messages[0].text == "executed response"
        assert handler_called

    async def test_function_middleware_conditional_no_next(self, mock_function: FunctionTool) -> None:
        """Test that when function middleware conditionally doesn't call next(), no execution happens."""

        class ConditionalNoNextFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                # Only call next() if argument name contains "execute"
                args = context.arguments
                assert isinstance(args, FunctionTestArgs)
                if "execute" in args.name:
                    await call_next()
                # Otherwise, don't call next() - no execution should happen

        middleware = ConditionalNoNextFunctionMiddleware()
        pipeline = FunctionMiddlewarePipeline(middleware)

        handler_called = False

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            nonlocal handler_called
            handler_called = True
            return "executed function result"

        # Test case where next() is NOT called
        no_execute_args = FunctionTestArgs(name="test_no_action")
        no_execute_context = FunctionInvocationContext(function=mock_function, arguments=no_execute_args)
        no_execute_result = await pipeline.execute(no_execute_context, final_handler)

        # When middleware doesn't call next(), function result should be None (functions can return None)
        assert no_execute_result is None
        assert not handler_called
        assert no_execute_context.result is None

        # Reset for next test
        handler_called = False

        # Test case where next() IS called
        execute_args = FunctionTestArgs(name="test_execute")
        execute_context = FunctionInvocationContext(function=mock_function, arguments=execute_args)
        execute_result = await pipeline.execute(execute_context, final_handler)

        assert execute_result == "executed function result"
        assert handler_called


class TestResultObservability:
    """Test cases for middleware result observability functionality."""

    async def test_agent_middleware_response_observability(self, mock_agent: SupportsAgentRun) -> None:
        """Test that middleware can observe response after execution."""
        observed_responses: list[AgentResponse] = []

        class ObservabilityMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Context should be empty before next()
                assert context.result is None

                # Call next to execute
                await call_next()

                # Context should now contain the response for observability
                assert context.result is not None
                assert isinstance(context.result, AgentResponse)
                observed_responses.append(context.result)

        middleware = ObservabilityMiddleware()
        pipeline = AgentMiddlewarePipeline(middleware)
        messages = [Message(role="user", text="test")]
        context = AgentContext(agent=mock_agent, messages=messages, stream=False)

        async def final_handler(ctx: AgentContext) -> AgentResponse:
            return AgentResponse(messages=[Message(role="assistant", text="executed response")])

        result = await pipeline.execute(context, final_handler)

        # Verify response was observed
        assert len(observed_responses) == 1
        assert observed_responses[0].messages[0].text == "executed response"
        assert result == observed_responses[0]

    async def test_function_middleware_result_observability(self, mock_function: FunctionTool) -> None:
        """Test that middleware can observe function result after execution."""
        observed_results: list[str] = []

        class ObservabilityMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                # Context should be empty before next()
                assert context.result is None

                # Call next to execute
                await call_next()

                # Context should now contain the result for observability
                assert context.result is not None
                observed_results.append(context.result)

        middleware = ObservabilityMiddleware()
        pipeline = FunctionMiddlewarePipeline(middleware)
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            return "executed function result"

        result = await pipeline.execute(context, final_handler)

        # Verify result was observed
        assert len(observed_results) == 1
        assert observed_results[0] == "executed function result"
        assert result == observed_results[0]

    async def test_agent_middleware_post_execution_override(self, mock_agent: SupportsAgentRun) -> None:
        """Test that middleware can override response after observing execution."""

        class PostExecutionOverrideMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Call next to execute first
                await call_next()

                # Now observe and conditionally override
                assert context.result is not None
                assert isinstance(context.result, AgentResponse)

                if "modify" in context.result.messages[0].text:
                    # Override after observing
                    context.result = AgentResponse(
                        messages=[Message(role="assistant", text="modified after execution")]
                    )

        middleware = PostExecutionOverrideMiddleware()
        pipeline = AgentMiddlewarePipeline(middleware)
        messages = [Message(role="user", text="test")]
        context = AgentContext(agent=mock_agent, messages=messages, stream=False)

        async def final_handler(ctx: AgentContext) -> AgentResponse:
            return AgentResponse(messages=[Message(role="assistant", text="response to modify")])

        result = await pipeline.execute(context, final_handler)

        # Verify response was modified after execution
        assert result is not None
        assert result.messages[0].text == "modified after execution"

    async def test_function_middleware_post_execution_override(self, mock_function: FunctionTool) -> None:
        """Test that middleware can override function result after observing execution."""

        class PostExecutionOverrideMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                # Call next to execute first
                await call_next()

                # Now observe and conditionally override
                assert context.result is not None

                if "modify" in context.result:
                    # Override after observing
                    context.result = "modified after execution"

        middleware = PostExecutionOverrideMiddleware()
        pipeline = FunctionMiddlewarePipeline(middleware)
        arguments = FunctionTestArgs(name="test")
        context = FunctionInvocationContext(function=mock_function, arguments=arguments)

        async def final_handler(ctx: FunctionInvocationContext) -> str:
            return "result to modify"

        result = await pipeline.execute(context, final_handler)

        # Verify result was modified after execution
        assert result == "modified after execution"


@pytest.fixture
def mock_agent() -> SupportsAgentRun:
    """Mock agent for testing."""
    agent = MagicMock(spec=SupportsAgentRun)
    agent.name = "test_agent"
    return agent


@pytest.fixture
def mock_function() -> FunctionTool:
    """Mock function for testing."""
    function = MagicMock(spec=FunctionTool)
    function.name = "test_function"
    return function
