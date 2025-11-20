# Copyright (c) Microsoft. All rights reserved.

"""Tests for kwargs propagation through as_tool() method."""

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import ChatAgent, ChatMessage, ChatResponse, FunctionCallContent, agent_middleware
from agent_framework._middleware import AgentRunContext

from .conftest import MockChatClient


class TestAsToolKwargsPropagation:
    """Test cases for kwargs propagation through as_tool() delegation."""

    async def test_as_tool_forwards_runtime_kwargs(self, chat_client: MockChatClient) -> None:
        """Test that runtime kwargs are forwarded through as_tool() to sub-agent."""
        captured_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            # Capture kwargs passed to the sub-agent
            captured_kwargs.update(context.kwargs)
            await next(context)

        # Setup mock response
        chat_client.responses = [
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response from sub-agent")]),
        ]

        # Create sub-agent with middleware
        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        # Create tool from sub-agent
        tool = sub_agent.as_tool(name="delegate", arg_name="task")

        # Directly invoke the tool with kwargs (simulating what happens during agent execution)
        _ = await tool.invoke(
            arguments=tool.input_model(task="Test delegation"),
            api_token="secret-xyz-123",
            user_id="user-456",
            session_id="session-789",
        )

        # Verify kwargs were forwarded to sub-agent
        assert "api_token" in captured_kwargs, f"Expected 'api_token' in {captured_kwargs}"
        assert captured_kwargs["api_token"] == "secret-xyz-123"
        assert "user_id" in captured_kwargs
        assert captured_kwargs["user_id"] == "user-456"
        assert "session_id" in captured_kwargs
        assert captured_kwargs["session_id"] == "session-789"

    async def test_as_tool_excludes_arg_name_from_forwarded_kwargs(self, chat_client: MockChatClient) -> None:
        """Test that the arg_name parameter is not forwarded as a kwarg."""
        captured_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            captured_kwargs.update(context.kwargs)
            await next(context)

        # Setup mock response
        chat_client.responses = [
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response from sub-agent")]),
        ]

        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool(arg_name="custom_task")

        # Invoke tool with both the arg_name field and additional kwargs
        await tool.invoke(
            arguments=tool.input_model(custom_task="Test task"),
            api_token="token-123",
            custom_task="should_be_excluded",  # This should be filtered out
        )

        # The arg_name ("custom_task") should NOT be in the forwarded kwargs
        assert "custom_task" not in captured_kwargs
        # But other kwargs should be present
        assert "api_token" in captured_kwargs
        assert captured_kwargs["api_token"] == "token-123"

    async def test_as_tool_nested_delegation_propagates_kwargs(self, chat_client: MockChatClient) -> None:
        """Test that kwargs propagate through multiple levels of delegation (A → B → C)."""
        captured_kwargs_list: list[dict[str, Any]] = []

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            # Capture kwargs at each level
            captured_kwargs_list.append(dict(context.kwargs))
            await next(context)

        # Setup mock responses to trigger nested tool invocation: B calls tool C, then completes.
        chat_client.responses = [
            ChatResponse(
                messages=[
                    ChatMessage(
                        role="assistant",
                        contents=[
                            FunctionCallContent(
                                call_id="call_c_1",
                                name="call_c",
                                arguments='{"task": "Please execute agent_c"}',
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response from agent_c")]),
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response from agent_b")]),
        ]

        # Create agent C (bottom level)
        agent_c = ChatAgent(
            chat_client=chat_client,
            name="agent_c",
            middleware=[capture_middleware],
        )

        # Create agent B (middle level) - delegates to C
        agent_b = ChatAgent(
            chat_client=chat_client,
            name="agent_b",
            tools=[agent_c.as_tool(name="call_c")],
            middleware=[capture_middleware],
        )

        # Create tool from B for direct invocation
        tool_b = agent_b.as_tool(name="call_b")

        # Invoke tool B with kwargs - should propagate to both B and C
        await tool_b.invoke(
            arguments=tool_b.input_model(task="Test cascade"),
            trace_id="trace-abc-123",
            tenant_id="tenant-xyz",
        )

        # Verify both levels received the kwargs
        # We should have 2 captures: one from B, one from C
        assert len(captured_kwargs_list) >= 2
        for kwargs_dict in captured_kwargs_list:
            assert kwargs_dict.get("trace_id") == "trace-abc-123"
            assert kwargs_dict.get("tenant_id") == "tenant-xyz"

    async def test_as_tool_streaming_mode_forwards_kwargs(self, chat_client: MockChatClient) -> None:
        """Test that kwargs are forwarded in streaming mode."""
        captured_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            captured_kwargs.update(context.kwargs)
            await next(context)

        # Setup mock streaming responses
        from agent_framework import ChatResponseUpdate, TextContent

        chat_client.streaming_responses = [
            [ChatResponseUpdate(text=TextContent(text="Streaming response"), role="assistant")],
        ]

        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        captured_updates: list[Any] = []

        async def stream_callback(update: Any) -> None:
            captured_updates.append(update)

        tool = sub_agent.as_tool(stream_callback=stream_callback)

        # Invoke tool with kwargs while streaming callback is active
        await tool.invoke(
            arguments=tool.input_model(task="Test streaming"),
            api_key="streaming-key-999",
        )

        # Verify kwargs were forwarded even in streaming mode
        assert "api_key" in captured_kwargs
        assert captured_kwargs["api_key"] == "streaming-key-999"
        assert len(captured_updates) == 1

    async def test_as_tool_empty_kwargs_still_works(self, chat_client: MockChatClient) -> None:
        """Test that as_tool works correctly when no extra kwargs are provided."""
        # Setup mock response
        chat_client.responses = [
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response from agent")]),
        ]

        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
        )

        tool = sub_agent.as_tool()

        # Invoke without any extra kwargs - should work without errors
        result = await tool.invoke(arguments=tool.input_model(task="Simple task"))

        # Verify tool executed successfully
        assert result is not None

    async def test_as_tool_kwargs_with_chat_options(self, chat_client: MockChatClient) -> None:
        """Test that kwargs including chat_options are properly forwarded."""
        captured_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            captured_kwargs.update(context.kwargs)
            await next(context)

        # Setup mock response
        chat_client.responses = [
            ChatResponse(messages=[ChatMessage(role="assistant", text="Response with options")]),
        ]

        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool()

        # Invoke with various kwargs
        await tool.invoke(
            arguments=tool.input_model(task="Test with options"),
            temperature=0.8,
            max_tokens=500,
            custom_param="custom_value",
        )

        # Verify all kwargs were forwarded
        assert "temperature" in captured_kwargs
        assert captured_kwargs["temperature"] == 0.8
        assert "max_tokens" in captured_kwargs
        assert captured_kwargs["max_tokens"] == 500
        assert "custom_param" in captured_kwargs
        assert captured_kwargs["custom_param"] == "custom_value"

    async def test_as_tool_kwargs_isolated_per_invocation(self, chat_client: MockChatClient) -> None:
        """Test that kwargs are isolated per invocation and don't leak between calls."""
        first_call_kwargs: dict[str, Any] = {}
        second_call_kwargs: dict[str, Any] = {}
        call_count = 0

        @agent_middleware
        async def capture_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_call_kwargs.update(context.kwargs)
            elif call_count == 2:
                second_call_kwargs.update(context.kwargs)
            await next(context)

        # Setup mock responses for both calls
        chat_client.responses = [
            ChatResponse(messages=[ChatMessage(role="assistant", text="First response")]),
            ChatResponse(messages=[ChatMessage(role="assistant", text="Second response")]),
        ]

        sub_agent = ChatAgent(
            chat_client=chat_client,
            name="sub_agent",
            middleware=[capture_middleware],
        )

        tool = sub_agent.as_tool()

        # First call with specific kwargs
        await tool.invoke(
            arguments=tool.input_model(task="First task"),
            session_id="session-1",
            api_token="token-1",
        )

        # Second call with different kwargs
        await tool.invoke(
            arguments=tool.input_model(task="Second task"),
            session_id="session-2",
            api_token="token-2",
        )

        # Verify first call had its own kwargs
        assert first_call_kwargs.get("session_id") == "session-1"
        assert first_call_kwargs.get("api_token") == "token-1"

        # Verify second call had its own kwargs (not leaked from first)
        assert second_call_kwargs.get("session_id") == "session-2"
        assert second_call_kwargs.get("api_token") == "token-2"
