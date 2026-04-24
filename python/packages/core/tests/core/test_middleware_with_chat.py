# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch

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
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("chat_middleware_before")
                await call_next()
                execution_order.append("chat_middleware_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [LoggingChatMiddleware()]

        # Execute chat client directly
        messages = [Message(role="user", contents=["test message"])]
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
        async def logging_chat_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("function_middleware_before")
            await call_next()
            execution_order.append("function_middleware_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [logging_chat_middleware]

        # Execute chat client directly
        messages = [Message(role="user", contents=["test message"])]
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
        async def message_modifier_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            # Modify the first message by adding a prefix
            if context.messages and len(context.messages) > 0:
                original_text = context.messages[0].text or ""
                context.messages[0] = Message(role=context.messages[0].role, contents=[f"MODIFIED: {original_text}"])
            await call_next()

        # Add middleware to chat client
        chat_client_base.chat_middleware = [message_modifier_middleware]

        # Execute chat client
        messages = [Message(role="user", contents=["test message"])]
        response = await chat_client_base.get_response(messages)

        # Verify that the message was modified (MockChatClient echoes back the input)
        assert response is not None
        assert len(response.messages) > 0
        # The mock client should receive the modified message
        assert "MODIFIED: test message" in response.messages[0].text

    async def test_chat_middleware_can_override_response(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that chat middleware can override the response."""

        @chat_middleware
        async def response_override_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            # Override the response without calling next()
            context.result = ChatResponse(
                messages=[Message(role="assistant", contents=["MiddlewareTypes overridden response"])],
                response_id="middleware-response-123",
            )
            context.terminate = True

        # Add middleware to chat client
        chat_client_base.chat_middleware = [response_override_middleware]

        # Execute chat client
        messages = [Message(role="user", contents=["test message"])]
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
        async def first_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("first_before")
            await call_next()
            execution_order.append("first_after")

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("second_before")
            await call_next()
            execution_order.append("second_after")

        # Add middleware to chat client (order should be preserved)
        chat_client_base.chat_middleware = [first_middleware, second_middleware]

        # Execute chat client
        messages = [Message(role="user", contents=["test message"])]
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
        async def agent_level_chat_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("agent_chat_middleware_before")
            await call_next()
            execution_order.append("agent_chat_middleware_after")

        client = MockBaseChatClient()

        # Create Agent with chat middleware
        agent = Agent(client=client, middleware=[agent_level_chat_middleware])

        # Execute the agent
        messages = [Message(role="user", contents=["test message"])]
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
        async def first_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("first_before")
            await call_next()
            execution_order.append("first_after")

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("second_before")
            await call_next()
            execution_order.append("second_after")

        # Create Agent with multiple chat middleware
        agent = Agent(client=chat_client_base, middleware=[first_middleware, second_middleware])

        # Execute the agent
        messages = [Message(role="user", contents=["test message"])]
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
        async def streaming_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("streaming_before")
            # Verify it's a streaming context
            assert context.stream is True

            def upper_case_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
                for content in update.contents:
                    if content.type == "text":
                        content.text = content.text.upper()
                return update

            context.stream_transform_hooks.append(upper_case_update)
            await call_next()
            execution_order.append("streaming_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [streaming_middleware]

        # Execute streaming response
        messages = [Message(role="user", contents=["test message"])]
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
        async def counting_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_count["count"] += 1
            await call_next()

        # First call with run-level middleware
        messages = [Message(role="user", contents=["first message"])]
        response1 = await chat_client_base.get_response(
            messages,
            client_kwargs={"middleware": [counting_middleware]},
        )
        assert response1 is not None
        assert execution_count["count"] == 1

        # Second call WITHOUT run-level middleware - should not execute the middleware
        messages = [Message(role="user", contents=["second message"])]
        response2 = await chat_client_base.get_response(messages)
        assert response2 is not None
        assert execution_count["count"] == 1  # Should still be 1, not 2

        # Third call with run-level middleware again - should execute
        messages = [Message(role="user", contents=["third message"])]
        response3 = await chat_client_base.get_response(
            messages,
            client_kwargs={"middleware": [counting_middleware]},
        )
        assert response3 is not None
        assert execution_count["count"] == 2  # Should be 2 now

    async def test_run_level_middleware_is_not_forwarded_to_inner_client(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that run-level middleware stays in the middleware pipeline only."""
        observed_context_kwargs: dict[str, Any] = {}

        @chat_middleware
        async def inspecting_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            observed_context_kwargs.update(context.kwargs)
            await call_next()

        async def fake_inner_get_response(**kwargs: Any) -> ChatResponse:
            assert "middleware" not in kwargs
            return ChatResponse(messages=[Message(role="assistant", contents=["ok"])])

        with patch.object(
            chat_client_base,
            "_inner_get_response",
            side_effect=fake_inner_get_response,
        ) as mock_inner_get_response:
            response = await chat_client_base.get_response(
                [Message(role="user", contents=["hello"])],
                client_kwargs={"middleware": [inspecting_middleware], "trace_id": "trace-123"},
            )

        assert response.messages[0].text == "ok"
        assert observed_context_kwargs == {"trace_id": "trace-123"}
        mock_inner_get_response.assert_called_once()

    async def test_chat_client_middleware_can_access_and_override_options(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that chat client middleware can access and override runtime options."""
        captured_options: dict[str, Any] = {}
        modified_options: dict[str, Any] = {}

        @chat_middleware
        async def kwargs_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            assert isinstance(context.options, dict)
            captured_options.update(context.options)

            context.options["temperature"] = 0.9
            context.options["max_tokens"] = 500
            context.options["new_param"] = "added_by_middleware"

            modified_options.update(context.options)

            await call_next()

        # Add middleware to chat client
        chat_client_base.chat_middleware = [kwargs_middleware]

        # Execute chat client with runtime options
        messages = [Message(role="user", contents=["test message"])]
        response = await chat_client_base.get_response(
            messages,
            options={"temperature": 0.7, "max_tokens": 100, "custom_param": "test_value"},
        )

        # Verify response
        assert response is not None
        assert len(response.messages) > 0

        assert captured_options["temperature"] == 0.7
        assert captured_options["max_tokens"] == 100
        assert captured_options["custom_param"] == "test_value"

        assert modified_options["temperature"] == 0.9
        assert modified_options["max_tokens"] == 500
        assert modified_options["new_param"] == "added_by_middleware"
        assert modified_options["custom_param"] == "test_value"

    def test_chat_middleware_pipeline_cache_reuses_matching_middleware(
        self,
        chat_client_base: "MockBaseChatClient",
    ) -> None:
        """Test that identical chat middleware sets reuse the cached pipeline."""

        @chat_middleware
        async def first_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        @chat_middleware
        async def second_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        first_pipeline = chat_client_base._get_chat_middleware_pipeline([first_middleware])
        second_pipeline = chat_client_base._get_chat_middleware_pipeline([first_middleware])
        third_pipeline = chat_client_base._get_chat_middleware_pipeline([second_middleware])

        assert first_pipeline is second_pipeline
        assert third_pipeline is not first_pipeline

    def test_chat_middleware_pipeline_cache_includes_base_middleware(
        self,
        chat_client_base: "MockBaseChatClient",
    ) -> None:
        """Test that chat middleware cache key includes base middleware to prevent incorrect reuse."""

        @chat_middleware
        async def base_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        @chat_middleware
        async def runtime_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        # Without base middleware
        pipeline_no_base = chat_client_base._get_chat_middleware_pipeline([runtime_middleware])

        # With base middleware
        chat_client_base.chat_middleware = [base_middleware]
        pipeline_with_base = chat_client_base._get_chat_middleware_pipeline([runtime_middleware])

        assert pipeline_with_base is not pipeline_no_base

    def test_function_middleware_pipeline_cache_reuses_matching_middleware(
        self,
        chat_client_base: "MockBaseChatClient",
    ) -> None:
        """Test that identical function middleware sets reuse the cached pipeline."""

        @function_middleware
        async def base_middleware(context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
            await call_next()

        @function_middleware
        async def first_runtime_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            await call_next()

        @function_middleware
        async def second_runtime_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            await call_next()

        chat_client_base.function_middleware = [base_middleware]

        first_pipeline = chat_client_base._get_function_middleware_pipeline([first_runtime_middleware])
        second_pipeline = chat_client_base._get_function_middleware_pipeline([first_runtime_middleware])
        third_pipeline = chat_client_base._get_function_middleware_pipeline([second_runtime_middleware])

        assert first_pipeline is second_pipeline
        assert third_pipeline is not first_pipeline

    async def test_function_middleware_registration_on_chat_client(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test function middleware registered on ChatClient is executed during function calls."""
        execution_order: list[str] = []

        @function_middleware
        async def test_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            nonlocal execution_order
            execution_order.append(f"function_middleware_before_{context.function.name}")
            await call_next()
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
            messages=[Message(role="assistant", contents=["Based on the weather data, it's sunny!"])]
        )

        client.run_responses = [function_call_response, final_response]
        # Execute the chat client directly with tools - this should trigger function invocation and middleware
        messages = [Message(role="user", contents=["What's the weather in San Francisco?"])]
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
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("run_level_function_middleware_before")
            await call_next()
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
        messages = [Message(role="user", contents=["What's the weather in New York?"])]
        response = await client.get_response(
            messages,
            options={"tools": [sample_tool_wrapped]},
            client_kwargs={"middleware": [run_level_function_middleware]},
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

    async def test_run_level_chat_and_function_middleware_split_per_function_loop_round(self) -> None:
        """Test mixed run-level middleware is split so chat middleware runs per model call."""
        execution_order: list[str] = []
        chat_round = 0

        @chat_middleware
        async def run_level_chat_middleware(
            context: ChatContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            nonlocal chat_round
            chat_round += 1
            execution_order.append(f"chat_middleware_before_{chat_round}")
            await call_next()
            execution_order.append(f"chat_middleware_after_{chat_round}")

        @function_middleware
        async def run_level_function_middleware(
            context: FunctionInvocationContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            execution_order.append("function_middleware_before")
            await call_next()
            execution_order.append("function_middleware_after")

        def sample_tool(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}: sunny"

        sample_tool_wrapped = FunctionTool(
            func=sample_tool,
            name="sample_tool",
            description="Get weather for a location",
            approval_mode="never_require",
        )

        client = MockBaseChatClient()
        client.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_3",
                                name="sample_tool",
                                arguments={"location": "Seattle"},
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", contents=["Based on the weather data, it's sunny!"])]),
        ]

        response = await client.get_response(
            [Message(role="user", contents=["What's the weather in Seattle?"])],
            options={"tools": [sample_tool_wrapped]},
            client_kwargs={"middleware": [run_level_chat_middleware, run_level_function_middleware]},
        )

        assert response is not None
        assert client.call_count == 2
        assert response.messages[-1].text == "Based on the weather data, it's sunny!"
        assert execution_order == [
            "chat_middleware_before_1",
            "chat_middleware_after_1",
            "function_middleware_before",
            "function_middleware_after",
            "chat_middleware_before_2",
            "chat_middleware_after_2",
        ]

    async def test_run_level_chat_and_function_middleware_split_per_function_loop_round_streaming(self) -> None:
        """Test mixed run-level middleware is split so chat middleware runs per model call in streaming mode."""
        execution_order: list[str] = []
        chat_round = 0

        @chat_middleware
        async def run_level_chat_middleware(
            context: ChatContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            nonlocal chat_round
            chat_round += 1
            execution_order.append(f"chat_middleware_before_{chat_round}")
            await call_next()
            execution_order.append(f"chat_middleware_after_{chat_round}")

        @function_middleware
        async def run_level_function_middleware(
            context: FunctionInvocationContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            execution_order.append("function_middleware_before")
            await call_next()
            execution_order.append("function_middleware_after")

        def sample_tool(location: str) -> str:
            """Get weather for a location."""
            return f"Weather in {location}: sunny"

        sample_tool_wrapped = FunctionTool(
            func=sample_tool,
            name="sample_tool",
            description="Get weather for a location",
            approval_mode="never_require",
        )

        client = MockBaseChatClient()
        client.streaming_responses = [
            [
                ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(
                            call_id="call_3",
                            name="sample_tool",
                            arguments='{"location": "Seattle"}',
                        )
                    ],
                    role="assistant",
                    finish_reason="tool_calls",
                ),
            ],
            [
                ChatResponseUpdate(
                    contents=[Content.from_text("Based on the weather data, it's sunny!")],
                    role="assistant",
                    finish_reason="stop",
                ),
            ],
        ]

        updates: list[ChatResponseUpdate] = []
        async for update in client.get_response(
            [Message(role="user", contents=["What's the weather in Seattle?"])],
            options={"tools": [sample_tool_wrapped]},
            client_kwargs={"middleware": [run_level_chat_middleware, run_level_function_middleware]},
            stream=True,
        ):
            updates.append(update)

        assert client.call_count == 2
        assert len(updates) > 0
        assert execution_order == [
            "chat_middleware_before_1",
            "chat_middleware_after_1",
            "function_middleware_before",
            "function_middleware_after",
            "chat_middleware_before_2",
            "chat_middleware_after_2",
        ]
