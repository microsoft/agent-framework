# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    Agent,
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationContext,
    FunctionTool,
    Message,
    SupportsChatGetResponse,
    chat_middleware,
    function_middleware,
)

from .conftest import MockBaseChatClient


class TestChatMiddleware:
    """Test cases for chat middleware functionality."""

    async def test_class_based_chat_middleware(self, chat_client_base: SupportsChatGetResponse) -> None:
        """Test class-based chat middleware with ChatClient."""
        execution_order: list[str] = []

        class LoggingChatMiddleware(ChatMiddleware):
            async def process(
                self,
                context: ChatContext,
                call_next: Callable[[ChatContext], Awaitable[None]],
            ) -> None:
                execution_order.append("chat_middleware_before")
                await call_next(context)
                execution_order.append("chat_middleware_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [LoggingChatMiddleware()]

        # Execute chat client directly
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"

        # Verify middleware execution order
        assert execution_order == ["chat_middleware_before", "chat_middleware_after"]

    async def test_function_based_chat_middleware(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test function-based chat middleware with ChatClient."""
        execution_order: list[str] = []

        @chat_middleware
        async def logging_chat_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_middleware_before")
            await call_next(context)
            execution_order.append("function_middleware_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [logging_chat_middleware]

        # Execute chat client directly
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"

        # Verify middleware execution order
        assert execution_order == ["function_middleware_before", "function_middleware_after"]

    async def test_chat_middleware_can_modify_messages(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that chat middleware can modify messages before sending to model."""

        @chat_middleware
        async def message_modifier_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            # Modify the first message by adding a prefix
            if context.messages and len(context.messages) > 0:
                original_text = context.messages[0].text or ""
                context.messages[0] = Message(role=context.messages[0].role, text=f"MODIFIED: {original_text}")
            await call_next(context)

        # Add middleware to chat client
        chat_client_base.chat_middleware = [message_modifier_middleware]

        # Execute chat client
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(messages)

        # Verify that the message was modified (MockChatClient echoes back the input)
        assert response is not None
        assert len(response.messages) > 0
        # The mock client should receive the modified message
        assert "MODIFIED: test message" in response.messages[0].text

    async def test_chat_middleware_can_override_response(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that chat middleware can override the response."""

        @chat_middleware
        async def response_override_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            # Override the response without calling next()
            context.result = ChatResponse(
                messages=[Message(role="assistant", text="MiddlewareTypes overridden response")],
                response_id="middleware-response-123",
            )
            context.terminate = True

        # Add middleware to chat client
        chat_client_base.chat_middleware = [response_override_middleware]

        # Execute chat client
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(messages)

        # Verify that the response was overridden
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].text == "MiddlewareTypes overridden response"
        assert response.response_id == "middleware-response-123"

    async def test_multiple_chat_middleware_execution_order(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that multiple chat middleware execute in the correct order."""
        execution_order: list[str] = []

        @chat_middleware
        async def first_middleware(context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]) -> None:
            execution_order.append("first_before")
            await call_next(context)
            execution_order.append("first_after")

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]) -> None:
            execution_order.append("second_before")
            await call_next(context)
            execution_order.append("second_after")

        # Add middleware to chat client (order should be preserved)
        chat_client_base.chat_middleware = [first_middleware, second_middleware]

        # Execute chat client
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(messages)

        # Verify response
        assert response is not None

        # Verify middleware execution order (nested execution)
        expected_order = [
            "first_before",
            "second_before",
            "second_after",
            "first_after",
        ]
        assert execution_order == expected_order

    async def test_chat_agent_with_chat_middleware(self) -> None:
        """Test Agent with chat middleware specified at agent level."""
        execution_order: list[str] = []

        @chat_middleware
        async def agent_level_chat_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            execution_order.append("agent_chat_middleware_before")
            await call_next(context)
            execution_order.append("agent_chat_middleware_after")

        client = MockBaseChatClient()

        # Create Agent with chat middleware
        agent = Agent(client=client, middleware=[agent_level_chat_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"

        # Verify middleware execution order
        assert execution_order == [
            "agent_chat_middleware_before",
            "agent_chat_middleware_after",
        ]

    async def test_chat_agent_with_multiple_chat_middleware(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that Agent can have multiple chat middleware."""
        execution_order: list[str] = []

        @chat_middleware
        async def first_middleware(context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]) -> None:
            execution_order.append("first_before")
            await call_next(context)
            execution_order.append("first_after")

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]) -> None:
            execution_order.append("second_before")
            await call_next(context)
            execution_order.append("second_after")

        # Create Agent with multiple chat middleware
        agent = Agent(client=chat_client_base, middleware=[first_middleware, second_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None

        # Verify both middleware executed (nested execution order)
        expected_order = [
            "first_before",
            "second_before",
            "second_after",
            "first_after",
        ]
        assert execution_order == expected_order

    async def test_chat_middleware_with_streaming(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test chat middleware with streaming responses."""
        execution_order: list[str] = []

        @chat_middleware
        async def streaming_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            execution_order.append("streaming_before")
            # Verify it's a streaming context
            assert context.stream is True

            def upper_case_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
                for content in update.contents:
                    if content.type == "text":
                        content.text = content.text.upper()
                return update

            context.stream_transform_hooks.append(upper_case_update)
            await call_next(context)
            execution_order.append("streaming_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [streaming_middleware]

        # Execute streaming response
        messages = [Message(role="user", text="test message")]
        updates: list[object] = []
        async for update in chat_client_base.get_response(messages, stream=True):
            updates.append(update)

        # Verify we got updates
        assert len(updates) > 0
        assert all(update.text == update.text.upper() for update in updates)

        # Verify middleware executed
        assert execution_order == ["streaming_before", "streaming_after"]

    async def test_run_level_middleware_isolation(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that run-level middleware is isolated and doesn't persist across calls."""
        execution_count = {"count": 0}

        @chat_middleware
        async def counting_middleware(
            context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]
        ) -> None:
            execution_count["count"] += 1
            await call_next(context)

        # First call with run-level middleware
        messages = [Message(role="user", text="first message")]
        response1 = await chat_client_base.get_response(messages, middleware=[counting_middleware])
        assert response1 is not None
        assert execution_count["count"] == 1

        # Second call WITHOUT run-level middleware - should not execute the middleware
        messages = [Message(role="user", text="second message")]
        response2 = await chat_client_base.get_response(messages)
        assert response2 is not None
        assert execution_count["count"] == 1  # Should still be 1, not 2

        # Third call with run-level middleware again - should execute
        messages = [Message(role="user", text="third message")]
        response3 = await chat_client_base.get_response(messages, middleware=[counting_middleware])
        assert response3 is not None
        assert execution_count["count"] == 2  # Should be 2 now

    async def test_chat_client_middleware_can_access_and_override_custom_kwargs(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that chat client middleware can access and override custom parameters like temperature."""
        captured_kwargs: dict[str, Any] = {}
        modified_kwargs: dict[str, Any] = {}

        @chat_middleware
        async def kwargs_middleware(context: ChatContext, call_next: Callable[[ChatContext], Awaitable[None]]) -> None:
            # Capture the original kwargs
            captured_kwargs.update(context.kwargs)

            # Modify some kwargs
            context.kwargs["temperature"] = 0.9
            context.kwargs["max_tokens"] = 500
            context.kwargs["new_param"] = "added_by_middleware"

            # Store modified kwargs for verification
            modified_kwargs.update(context.kwargs)

            await call_next(context)

        # Add middleware to chat client
        chat_client_base.chat_middleware = [kwargs_middleware]

        # Execute chat client with custom parameters
        messages = [Message(role="user", text="test message")]
        response = await chat_client_base.get_response(
            messages, temperature=0.7, max_tokens=100, custom_param="test_value"
        )

        # Verify response
        assert response is not None
        assert len(response.messages) > 0

        assert captured_kwargs["temperature"] == 0.7
        assert captured_kwargs["max_tokens"] == 100
        assert captured_kwargs["custom_param"] == "test_value"

        # Verify middleware could modify the kwargs
        assert modified_kwargs["temperature"] == 0.9
        assert modified_kwargs["max_tokens"] == 500
        assert modified_kwargs["new_param"] == "added_by_middleware"
        assert modified_kwargs["custom_param"] == "test_value"  # Should still be there

    async def test_function_middleware_registration_on_chat_client(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test function middleware registered on ChatClient is executed during function calls."""
        execution_order: list[str] = []

        @function_middleware
        async def test_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            nonlocal execution_order
            execution_order.append(f"function_middleware_before_{context.function.name}")
            await call_next(context)
            execution_order.append(f"function_middleware_after_{context.function.name}")

        # Define a simple tool function
        def sample_tool(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}: sunny"

        sample_tool_wrapped = FunctionTool(
            func=sample_tool,
            name="sample_tool",
            description="Get weather for a location",
            approval_mode="never_require",
        )

        # Create function-invocation enabled chat client (MockBaseChatClient already includes FunctionInvocationLayer)
        client = MockBaseChatClient()

        # Set function middleware directly on the chat client
        client.function_middleware = [test_function_middleware]

        # Prepare responses that will trigger function invocation
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_1",
                            name="sample_tool",
                            arguments={"location": "San Francisco"},
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(
            messages=[Message(role="assistant", text="Based on the weather data, it's sunny!")]
        )

        client.run_responses = [function_call_response, final_response]
        # Execute the chat client directly with tools - this should trigger function invocation and middleware
        messages = [Message(role="user", text="What's the weather in San Francisco?")]
        response = await client.get_response(messages, options={"tools": [sample_tool_wrapped]})

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert client.call_count == 2  # Two calls: function call + final response

        # Verify function middleware was executed
        assert execution_order == [
            "function_middleware_before_sample_tool",
            "function_middleware_after_sample_tool",
        ]

    async def test_run_level_function_middleware(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that function middleware passed to get_response method is also invoked."""
        execution_order: list[str] = []

        @function_middleware
        async def run_level_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("run_level_function_middleware_before")
            await call_next(context)
            execution_order.append("run_level_function_middleware_after")

        # Define a simple tool function
        def sample_tool(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}: sunny"

        sample_tool_wrapped = FunctionTool(
            func=sample_tool,
            name="sample_tool",
            description="Get weather for a location",
            approval_mode="never_require",
        )

        # Create function-invocation enabled chat client (MockBaseChatClient already includes FunctionInvocationLayer)
        client = MockBaseChatClient()

        # Prepare responses that will trigger function invocation
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_2",
                            name="sample_tool",
                            arguments={"location": "New York"},
                        )
                    ],
                )
            ]
        )
        client.run_responses = [function_call_response]

        # Execute the chat client directly with run-level middleware and tools
        messages = [Message(role="user", text="What's the weather in New York?")]
        response = await client.get_response(
            messages, options={"tools": [sample_tool_wrapped]}, middleware=[run_level_function_middleware]
        )

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert client.call_count == 2  # Two calls: function call + final response

        # Verify run-level function middleware was executed once (during function invocation)
        assert execution_order == [
            "run_level_function_middleware_before",
            "run_level_function_middleware_after",
        ]
