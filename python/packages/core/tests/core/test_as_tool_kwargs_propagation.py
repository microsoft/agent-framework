# Copyright (c) Microsoft. All rights reserved.

"""Tests for kwargs propagation through as_tool() method."""

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import Agent, ChatResponse, Content, Message, agent_middleware
from agent_framework._middleware import AgentContext, FunctionInvocationContext

from .conftest import MockChatClient


class TestAsToolKwargsPropagation:
    """Test cases for kwargs propagation through as_tool() delegation."""

    @staticmethod
    def _build_context(
        tool: Any,
        *,
        task: str,
        runtime_kwargs: dict[str, Any] | None = None,
    ) -> FunctionInvocationContext:
        return FunctionInvocationContext(
            function=tool,
            arguments={"task": task},
            kwargs=runtime_kwargs,
        )

    async def test_as_tool_forwards_runtime_kwargs(self, client: MockChatClient) -> None:
        """Test that runtime kwargs are forwarded through as_tool() to sub-agent tools."""
        captured_kwargs: dict[str, Any] = {}
        captured_function_invocation_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_kwargs.update(context.kwargs)
            captured_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock response
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["Response from sub-agent"])]),
        ]

        # Create sub-agent with middleware
        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        # Create tool from sub-agent
        tool = sub_agent.as_tool(name="delegate", arg_name="task")

        # Directly invoke the tool with explicit runtime context (simulating agent execution).
        _ = await tool.invoke(
            context=self._build_context(
                tool,
                task="Test delegation",
                runtime_kwargs={
                    "api_token": "secret-xyz-123",
                    "user_id": "user-456",
                    "session_id": "session-789",
                },
            ),
        )

        assert captured_kwargs == {}
        assert captured_function_invocation_kwargs["api_token"] == "secret-xyz-123"
        assert captured_function_invocation_kwargs["user_id"] == "user-456"
        assert captured_function_invocation_kwargs["session_id"] == "session-789"

    async def test_as_tool_forwards_context_kwargs_verbatim(self, client: MockChatClient) -> None:
        """Test that runtime kwargs are forwarded exactly from FunctionInvocationContext.kwargs."""
        captured_function_invocation_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock response
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["Response from sub-agent"])]),
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool(arg_name="custom_task")

        # Invoke tool with both the arg_name field and additional kwargs
        await tool.invoke(
            context=FunctionInvocationContext(
                function=tool,
                arguments={"custom_task": "Test task"},
                kwargs={
                    "api_token": "token-123",
                    "custom_task": "should_be_excluded",
                },
            )
        )

        assert captured_function_invocation_kwargs["custom_task"] == "should_be_excluded"
        assert captured_function_invocation_kwargs["api_token"] == "token-123"

    async def test_as_tool_nested_delegation_propagates_kwargs(self, client: MockChatClient) -> None:
        """Test that runtime kwargs propagate through multiple levels of delegation (A -> B -> C)."""
        captured_function_invocation_kwargs_list: list[dict[str, Any]] = []

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_function_invocation_kwargs_list.append(dict(context.function_invocation_kwargs))
            await call_next()

        # Setup mock responses to trigger nested tool invocation: B calls tool C, then completes.
        client.responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_c_1",
                                name="call_c",
                                arguments='{"task": "Please execute agent_c"}',
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", contents=["Response from agent_c"])]),
            ChatResponse(messages=[Message(role="assistant", contents=["Response from agent_b"])]),
        ]

        # Create agent C (bottom level)
        agent_c = Agent(
            client=client,
            name="agent_c",
            middleware=[capture_middleware],
        )

        # Create agent B (middle level) - delegates to C
        agent_b = Agent(
            client=client,
            name="agent_b",
            tools=[agent_c.as_tool(name="call_c")],
            middleware=[capture_middleware],
        )

        # Create tool from B for direct invocation
        tool_b = agent_b.as_tool(name="call_b")

        # Invoke tool B with kwargs - should propagate to both B and C
        await tool_b.invoke(
            context=self._build_context(
                tool_b,
                task="Test cascade",
                runtime_kwargs={
                    "trace_id": "trace-abc-123",
                    "tenant_id": "tenant-xyz",
                },
            ),
        )

        assert len(captured_function_invocation_kwargs_list) >= 1
        assert captured_function_invocation_kwargs_list[0].get("trace_id") == "trace-abc-123"
        assert captured_function_invocation_kwargs_list[0].get("tenant_id") == "tenant-xyz"

    async def test_as_tool_streaming_mode_forwards_kwargs(self, client: MockChatClient) -> None:
        """Test that runtime kwargs are forwarded in streaming mode."""
        captured_kwargs: dict[str, Any] = {}
        captured_function_invocation_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_kwargs.update(context.kwargs)
            captured_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock streaming responses
        from agent_framework import ChatResponseUpdate

        client.streaming_responses = [
            [ChatResponseUpdate(contents=[Content.from_text(text="Streaming response")], role="assistant")],
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        captured_updates: list[Any] = []

        async def stream_callback(update: Any) -> None:
            captured_updates.append(update)

        tool = sub_agent.as_tool(stream_callback=stream_callback)

        # Invoke tool with kwargs while streaming callback is active
        await tool.invoke(
            context=self._build_context(
                tool,
                task="Test streaming",
                runtime_kwargs={"api_key": "streaming-key-999"},
            ),
        )

        assert captured_kwargs == {}
        assert captured_function_invocation_kwargs["api_key"] == "streaming-key-999"
        assert len(captured_updates) == 1

    async def test_as_tool_empty_kwargs_still_works(self, client: MockChatClient) -> None:
        """Test that as_tool works correctly when no extra kwargs are provided."""
        # Setup mock response
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["Response from agent"])]),
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
        )

        tool = sub_agent.as_tool()

        # Invoke without any extra kwargs - should work without errors
        result = await tool.invoke(arguments={"task": "Simple task"})

        # Verify tool executed successfully
        assert result is not None

    async def test_as_tool_kwargs_with_chat_options(self, client: MockChatClient) -> None:
        """Test that runtime kwargs are forwarded only via function_invocation_kwargs."""
        captured_kwargs: dict[str, Any] = {}
        captured_function_invocation_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_kwargs.update(context.kwargs)
            captured_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock response
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["Response with options"])]),
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool()

        # Invoke with various kwargs
        await tool.invoke(
            context=self._build_context(
                tool,
                task="Test with options",
                runtime_kwargs={
                    "temperature": 0.8,
                    "max_tokens": 500,
                    "custom_param": "custom_value",
                },
            ),
        )

        assert captured_kwargs == {}
        assert captured_function_invocation_kwargs["temperature"] == 0.8
        assert captured_function_invocation_kwargs["max_tokens"] == 500
        assert captured_function_invocation_kwargs["custom_param"] == "custom_value"

    async def test_as_tool_kwargs_isolated_per_invocation(self, client: MockChatClient) -> None:
        """Test that runtime kwargs are isolated per invocation and don't leak between calls."""
        first_call_function_invocation_kwargs: dict[str, Any] = {}
        second_call_function_invocation_kwargs: dict[str, Any] = {}
        call_count = 0

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_call_function_invocation_kwargs.update(context.function_invocation_kwargs)
            elif call_count == 2:
                second_call_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock responses for both calls
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["First response"])]),
            ChatResponse(messages=[Message(role="assistant", contents=["Second response"])]),
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool()

        # First call with specific kwargs
        await tool.invoke(
            context=self._build_context(
                tool,
                task="First task",
                runtime_kwargs={"session_id": "session-1", "api_token": "token-1"},
            ),
        )

        # Second call with different kwargs
        await tool.invoke(
            context=self._build_context(
                tool,
                task="Second task",
                runtime_kwargs={"session_id": "session-2", "api_token": "token-2"},
            ),
        )

        assert first_call_function_invocation_kwargs.get("session_id") == "session-1"
        assert first_call_function_invocation_kwargs.get("api_token") == "token-1"

        assert second_call_function_invocation_kwargs.get("session_id") == "session-2"
        assert second_call_function_invocation_kwargs.get("api_token") == "token-2"

    async def test_as_tool_forwards_conversation_id_from_context_kwargs(self, client: MockChatClient) -> None:
        """Test that conversation_id is forwarded when explicitly present in runtime context kwargs."""
        captured_function_invocation_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            captured_function_invocation_kwargs.update(context.function_invocation_kwargs)
            await call_next()

        # Setup mock response
        client.responses = [
            ChatResponse(messages=[Message(role="assistant", contents=["Response from sub-agent"])]),
        ]

        sub_agent = Agent(
            client=client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool(name="delegate", arg_name="task")

        # Invoke tool with conversation_id in kwargs (simulating parent's conversation state)
        await tool.invoke(
            context=self._build_context(
                tool,
                task="Test delegation",
                runtime_kwargs={
                    "conversation_id": "conv-parent-456",
                    "api_token": "secret-xyz-123",
                    "user_id": "user-456",
                },
            ),
        )

        assert captured_function_invocation_kwargs.get("conversation_id") == "conv-parent-456"
        assert captured_function_invocation_kwargs.get("api_token") == "secret-xyz-123"
        assert captured_function_invocation_kwargs.get("user_id") == "user-456"
