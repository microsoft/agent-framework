# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    AgentResponseUpdate,
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationContext,
    FunctionMiddleware,
    FunctionTool,
    Message,
    MiddlewareException,
    MiddlewareTermination,
    MiddlewareType,
    SupportsChatGetResponse,
    agent_middleware,
    chat_middleware,
    function_middleware,
)
from agent_framework._sessions import InMemoryHistoryProvider

from .conftest import MockBaseChatClient, MockChatClient

# region Agent Tests


class TestChatAgentClassBasedMiddleware:
    """Test cases for class-based middleware integration with Agent."""

    async def test_class_based_agent_middleware_with_chat_agent(self, client: SupportsChatGetResponse) -> None:
        """Test class-based agent middleware with Agent."""
        execution_order: list[str] = []

        class TrackingAgentMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append(f"{self.name}_before")
                await call_next()
                execution_order.append(f"{self.name}_after")

        # Create Agent with middleware
        middleware = TrackingAgentMiddleware("agent_middleware")
        agent = Agent(client=client, middleware=[middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"
        # Note: conftest "MockChatClient" returns different text format
        assert "test response" in response.messages[0].text

        # Verify middleware execution order
        assert execution_order == ["agent_middleware_before", "agent_middleware_after"]

    async def test_class_based_function_middleware_with_chat_agent(self, client: "MockChatClient") -> None:
        """Test class-based function middleware with Agent."""

        class TrackingFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                await call_next()

        middleware = TrackingFunctionMiddleware()
        Agent(client=client, middleware=[middleware])

    async def test_class_based_function_middleware_with_chat_agent_supported_client(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test class-based function middleware with Agent using a full chat client."""
        execution_order: list[str] = []

        class TrackingFunctionMiddleware(FunctionMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await call_next()
                execution_order.append(f"{self.name}_after")

        middleware = TrackingFunctionMiddleware("function_middleware")
        agent = Agent(client=chat_client_base, middleware=[middleware])

        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 1
        assert execution_order == []


class TestChatAgentFunctionBasedMiddleware:
    """Test cases for function-based middleware integration with Agent."""

    async def test_agent_middleware_with_pre_termination(self, client: "MockChatClient") -> None:
        """Test that agent middleware can terminate execution before calling next()."""
        execution_order: list[str] = []

        class PreTerminationMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("middleware_before")
                raise MiddlewareTermination
                # Code after raise is unreachable
                await call_next()
                execution_order.append("middleware_after")

        # Create Agent with terminating middleware
        middleware = PreTerminationMiddleware()
        agent = Agent(client=client, middleware=[middleware])

        # Execute the agent with multiple messages
        messages = [
            Message(role="user", text="message1"),
            Message(role="user", text="message2"),  # This should not be processed due to termination
        ]
        response = await agent.run(messages)

        # Verify response - MiddlewareTermination before next() returns None
        assert response is None
        # Only middleware_before runs - middleware_after is unreachable after raise
        assert execution_order == ["middleware_before"]
        assert client.call_count == 0  # No calls should be made due to termination

    async def test_agent_middleware_with_post_termination(self, client: "MockChatClient") -> None:
        """Test that agent middleware can terminate execution after calling next()."""
        execution_order: list[str] = []

        class PostTerminationMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("middleware_before")
                await call_next()
                execution_order.append("middleware_after")
                context.terminate = True

        # Create Agent with terminating middleware
        middleware = PostTerminationMiddleware()
        agent = Agent(client=client, middleware=[middleware])

        # Execute the agent with multiple messages
        messages = [
            Message(role="user", text="message1"),
            Message(role="user", text="message2"),
        ]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) == 1
        assert response.messages[0].role == "assistant"
        assert "test response" in response.messages[0].text

        # Verify middleware execution order
        assert execution_order == [
            "middleware_before",
            "middleware_after",
        ]
        assert client.call_count == 1

    async def test_function_middleware_with_pre_termination(self, client: "MockChatClient") -> None:
        """Test that function middleware can terminate execution before calling next()."""
        execution_order: list[str] = []

        class PreTerminationFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("middleware_before")
                context.terminate = True
                # We call next() but since terminate=True, subsequent middleware and handler should not execute
                await call_next()
                execution_order.append("middleware_after")

        Agent(client=client, middleware=[PreTerminationFunctionMiddleware()], tools=[])

    async def test_function_middleware_with_post_termination(self, client: "MockChatClient") -> None:
        """Test that function middleware can terminate execution after calling next()."""
        execution_order: list[str] = []

        class PostTerminationFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("middleware_before")
                await call_next()
                execution_order.append("middleware_after")
                context.terminate = True

        Agent(client=client, middleware=[PostTerminationFunctionMiddleware()], tools=[])

    async def test_function_based_agent_middleware_with_chat_agent(self, client: "MockChatClient") -> None:
        """Test function-based agent middleware with Agent."""
        execution_order: list[str] = []

        async def tracking_agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("agent_function_before")
            await call_next()
            execution_order.append("agent_function_after")

        # Create Agent with function middleware
        agent = Agent(client=client, middleware=[tracking_agent_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"
        assert response.messages[0].text == "test response"
        assert client.call_count == 1

        # Verify middleware execution order
        assert execution_order == ["agent_function_before", "agent_function_after"]

    async def test_function_based_function_middleware_with_chat_agent(self, client: "MockChatClient") -> None:
        """Test function-based function middleware with Agent."""

        async def tracking_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            await call_next()

        Agent(client=client, middleware=[tracking_function_middleware])

    async def test_function_based_function_middleware_with_supported_client(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test function-based function middleware with Agent using a full chat client."""
        execution_order: list[str] = []

        async def tracking_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await call_next()
            execution_order.append("function_function_after")

        agent = Agent(client=chat_client_base, middleware=[tracking_function_middleware])
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 1
        assert execution_order == []


class TestChatAgentStreamingMiddleware:
    """Test cases for streaming middleware integration with Agent."""

    async def test_agent_middleware_with_streaming(self, client: "MockChatClient") -> None:
        """Test agent middleware with streaming Agent responses."""
        execution_order: list[str] = []
        streaming_flags: list[bool] = []

        class StreamingTrackingMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("middleware_before")
                streaming_flags.append(context.stream)
                await call_next()
                execution_order.append("middleware_after")

        # Create Agent with middleware
        middleware = StreamingTrackingMiddleware()
        agent = Agent(client=client, middleware=[middleware])

        # Set up mock streaming responses
        client.streaming_responses = [
            [
                ChatResponseUpdate(contents=[Content.from_text(text="Streaming")], role="assistant"),
                ChatResponseUpdate(contents=[Content.from_text(text=" response")], role="assistant"),
            ]
        ]

        # Execute streaming
        messages = [Message(role="user", text="test message")]
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run(messages, stream=True):
            updates.append(update)

        # Verify streaming response
        assert len(updates) == 2
        assert updates[0].text == "Streaming"
        assert updates[1].text == " response"
        assert client.call_count == 1

        # Verify middleware was called and streaming flag was set correctly
        assert execution_order == [
            "middleware_before",
            "middleware_after",
        ]
        assert streaming_flags == [True]  # Context should indicate streaming

    async def test_non_streaming_vs_streaming_flag_validation(self, client: "MockChatClient") -> None:
        """Test that stream flag is correctly set for different execution modes."""
        streaming_flags: list[bool] = []

        class FlagTrackingMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                streaming_flags.append(context.stream)
                await call_next()

        # Create Agent with middleware
        middleware = FlagTrackingMiddleware()
        agent = Agent(client=client, middleware=[middleware])
        messages = [Message(role="user", text="test message")]

        # Test non-streaming execution
        response = await agent.run(messages)
        assert response is not None

        # Test streaming execution
        async for _ in agent.run(messages, stream=True):
            pass

        # Verify flags: [non-streaming, streaming]
        assert streaming_flags == [False, True]


class TestChatAgentMultipleMiddlewareOrdering:
    """Test cases for multiple middleware execution order with Agent."""

    async def test_multiple_agent_middleware_execution_order(self, client: "MockChatClient") -> None:
        """Test that multiple agent middleware execute in correct order with Agent."""
        execution_order: list[str] = []

        class OrderedMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append(f"{self.name}_before")
                await call_next()
                execution_order.append(f"{self.name}_after")

        # Create multiple middleware
        middleware1 = OrderedMiddleware("first")
        middleware2 = OrderedMiddleware("second")
        middleware3 = OrderedMiddleware("third")

        # Create Agent with multiple middleware
        agent = Agent(client=client, middleware=[middleware1, middleware2, middleware3])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert client.call_count == 1

        # Verify execution order (should be nested: first wraps second wraps third)
        expected_order = ["first_before", "second_before", "third_before", "third_after", "second_after", "first_after"]
        assert execution_order == expected_order

    async def test_mixed_middleware_types_with_chat_agent(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test mixed class and function-based middleware with Agent."""
        execution_order: list[str] = []

        class ClassAgentMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("class_agent_before")
                await call_next()
                execution_order.append("class_agent_after")

        async def function_agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("function_agent_before")
            await call_next()
            execution_order.append("function_agent_after")

        class ClassFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("class_function_before")
                await call_next()
                execution_order.append("class_function_after")

        async def function_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await call_next()
            execution_order.append("function_function_after")

        agent = Agent(
            client=chat_client_base,
            middleware=[
                ClassAgentMiddleware(),
                function_agent_middleware,
                ClassFunctionMiddleware(),
                function_function_middleware,
            ],
        )
        await agent.run([Message(role="user", text="test")])

    async def test_mixed_middleware_types_with_supported_client(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test mixed class and function-based middleware with a full chat client."""
        execution_order: list[str] = []

        class ClassAgentMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("class_agent_before")
                await call_next()
                execution_order.append("class_agent_after")

        async def function_agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("function_agent_before")
            await call_next()
            execution_order.append("function_agent_after")

        async def function_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await call_next()
            execution_order.append("function_function_after")

        agent = Agent(
            client=chat_client_base,
            middleware=[
                ClassAgentMiddleware(),
                function_agent_middleware,
                function_function_middleware,
            ],
        )

        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        assert response is not None
        assert chat_client_base.call_count == 1
        expected_order = ["class_agent_before", "function_agent_before", "function_agent_after", "class_agent_after"]
        assert execution_order == expected_order


# region Tool Functions for Testing


def _sample_tool_function_impl(location: str) -> str:
    """A simple tool function for middleware testing."""
    return f"Weather in {location}: sunny"


sample_tool_function = FunctionTool(
    func=_sample_tool_function_impl,
    name="sample_tool_function",
    description="A simple tool function for middleware testing.",
    approval_mode="never_require",
)


# region Agent Function MiddlewareTypes Tests with Tools


class TestChatAgentFunctionMiddlewareWithTools:
    """Test cases for function middleware integration with Agent when tools are used."""

    async def test_class_based_function_middleware_with_tool_calls(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test class-based function middleware with Agent when function calls are made."""
        execution_order: list[str] = []

        class TrackingFunctionMiddleware(FunctionMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append(f"{self.name}_before")
                await call_next()
                execution_order.append(f"{self.name}_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_123",
                            name="sample_tool_function",
                            arguments='{"location": "Seattle"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])

        chat_client_base.run_responses = [function_call_response, final_response]

        # Create Agent with function middleware and tools
        middleware = TrackingFunctionMiddleware("function_middleware")
        agent = Agent(
            client=chat_client_base,
            middleware=[middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [Message(role="user", text="Get weather for Seattle")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 2  # Two calls: one for function call, one for final response

        # Verify function middleware was executed
        assert execution_order == ["function_middleware_before", "function_middleware_after"]

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if c.type == "function_call"]
        function_results = [c for c in all_contents if c.type == "function_result"]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id

    async def test_function_based_function_middleware_with_tool_calls(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test function-based function middleware with Agent when function calls are made."""
        execution_order: list[str] = []

        async def tracking_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("function_middleware_before")
            await call_next()
            execution_order.append("function_middleware_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_456",
                            name="sample_tool_function",
                            arguments='{"location": "San Francisco"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])

        chat_client_base.run_responses = [function_call_response, final_response]

        # Create Agent with function middleware and tools
        agent = Agent(
            client=chat_client_base,
            middleware=[tracking_function_middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [Message(role="user", text="Get weather for San Francisco")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 2  # Two calls: one for function call, one for final response

        # Verify function middleware was executed
        assert execution_order == ["function_middleware_before", "function_middleware_after"]

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if c.type == "function_call"]
        function_results = [c for c in all_contents if c.type == "function_result"]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id

    async def test_mixed_agent_and_function_middleware_with_tool_calls(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test both agent and function middleware with Agent when function calls are made."""
        execution_order: list[str] = []

        class TrackingAgentMiddleware(AgentMiddleware):
            async def process(
                self,
                context: AgentContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("agent_middleware_before")
                await call_next()
                execution_order.append("agent_middleware_after")

        class TrackingFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_order.append("function_middleware_before")
                await call_next()
                execution_order.append("function_middleware_after")

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_789",
                            name="sample_tool_function",
                            arguments='{"location": "New York"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])

        chat_client_base.run_responses = [function_call_response, final_response]

        # Create Agent with both agent and function middleware and tools
        agent = Agent(
            client=chat_client_base,
            middleware=[TrackingAgentMiddleware(), TrackingFunctionMiddleware()],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [Message(role="user", text="Get weather for New York")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 2  # Two calls: one for function call, one for final response

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
        function_calls = [c for c in all_contents if c.type == "function_call"]
        function_results = [c for c in all_contents if c.type == "function_result"]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "sample_tool_function"
        assert function_results[0].call_id == function_calls[0].call_id

    async def test_function_middleware_can_access_and_override_custom_kwargs(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that function middleware can access and override custom parameters."""
        captured_kwargs: dict[str, Any] = {}
        modified_kwargs: dict[str, Any] = {}
        middleware_called = False

        @function_middleware
        async def kwargs_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            nonlocal middleware_called
            middleware_called = True

            # Capture the original kwargs
            captured_kwargs["has_custom_param"] = "custom_param" in context.kwargs
            captured_kwargs["custom_param"] = context.kwargs.get("custom_param")

            # Modify some kwargs
            context.kwargs["temperature"] = 0.9
            context.kwargs["max_tokens"] = 500
            context.kwargs["new_param"] = "added_by_middleware"

            # Store modified kwargs for verification
            modified_kwargs["temperature"] = context.kwargs.get("temperature")
            modified_kwargs["max_tokens"] = context.kwargs.get("max_tokens")
            modified_kwargs["new_param"] = context.kwargs.get("new_param")
            modified_kwargs["custom_param"] = context.kwargs.get("custom_param")

            await call_next()

        chat_client_base.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="test_call", name="sample_tool_function", arguments={"location": "Seattle"}
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", contents=[Content.from_text("Function completed")])]),
        ]

        # Create Agent with function middleware
        agent = Agent(client=chat_client_base, middleware=[kwargs_middleware], tools=[sample_tool_function])

        # Execute the agent with custom parameters passed as kwargs
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages, options={"additional_function_arguments": {"custom_param": "test_value"}})

        # Verify response
        assert response is not None
        assert len(response.messages) > 0

        # First check if middleware was called at all
        assert middleware_called, "Function middleware was not called"

        # Verify middleware captured the original kwargs
        assert captured_kwargs["has_custom_param"] is True
        assert captured_kwargs["custom_param"] == "test_value"

        # Verify middleware could modify the kwargs
        assert modified_kwargs["temperature"] == 0.9
        assert modified_kwargs["max_tokens"] == 500
        assert modified_kwargs["new_param"] == "added_by_middleware"
        assert modified_kwargs["custom_param"] == "test_value"


class TestMiddlewareDynamicRebuild:
    """Test cases for dynamic middleware pipeline rebuilding with Agent."""

    class TrackingAgentMiddleware(AgentMiddleware):
        """Test middleware that tracks execution."""

        def __init__(self, name: str, execution_log: list[str]):
            self.name = name
            self.execution_log = execution_log

        async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            self.execution_log.append(f"{self.name}_start")
            await call_next()
            self.execution_log.append(f"{self.name}_end")

    async def test_middleware_dynamic_rebuild_non_streaming(self, client: "MockChatClient") -> None:
        """Test that middleware pipeline is rebuilt when agent.middleware collection is modified for non-streaming."""
        execution_log: list[str] = []

        # Create agent with initial middleware
        middleware1 = self.TrackingAgentMiddleware("middleware1", execution_log)
        agent = Agent(client=client, middleware=[middleware1])

        # First execution - should use middleware1
        await agent.run("Test message 1")
        assert "middleware1_start" in execution_log
        assert "middleware1_end" in execution_log

        # Clear execution log
        execution_log.clear()

        # Modify the middleware collection by adding another middleware
        middleware2 = self.TrackingAgentMiddleware("middleware2", execution_log)
        agent.middleware = [middleware1, middleware2]

        # Second execution - should use both middleware1 and middleware2
        await agent.run("Test message 2")
        assert "middleware1_start" in execution_log
        assert "middleware1_end" in execution_log
        assert "middleware2_start" in execution_log
        assert "middleware2_end" in execution_log

        # Clear execution log
        execution_log.clear()

        # Modify the middleware collection by replacing with just middleware2
        agent.middleware = [middleware2]

        # Third execution - should use only middleware2
        await agent.run("Test message 3")
        assert "middleware1_start" not in execution_log
        assert "middleware1_end" not in execution_log
        assert "middleware2_start" in execution_log
        assert "middleware2_end" in execution_log

        # Clear execution log
        execution_log.clear()

        # Remove all middleware
        agent.middleware = []

        # Fourth execution - should use no middleware
        await agent.run("Test message 4")
        assert len(execution_log) == 0

    async def test_middleware_dynamic_rebuild_streaming(self, client: "MockChatClient") -> None:
        """Test that middleware pipeline is rebuilt for streaming when agent.middleware collection is modified."""
        execution_log: list[str] = []

        # Create agent with initial middleware
        middleware1 = self.TrackingAgentMiddleware("stream_middleware1", execution_log)
        agent = Agent(client=client, middleware=[middleware1])

        # First streaming execution
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Test stream message 1", stream=True):
            updates.append(update)

        assert "stream_middleware1_start" in execution_log
        assert "stream_middleware1_end" in execution_log

        # Clear execution log
        execution_log.clear()

        # Modify the middleware collection
        middleware2 = self.TrackingAgentMiddleware("stream_middleware2", execution_log)
        agent.middleware = [middleware2]

        # Second streaming execution - should use only middleware2
        updates = []
        async for update in agent.run("Test stream message 2", stream=True):
            updates.append(update)

        assert "stream_middleware1_start" not in execution_log
        assert "stream_middleware1_end" not in execution_log
        assert "stream_middleware2_start" in execution_log
        assert "stream_middleware2_end" in execution_log

    async def test_middleware_order_change_detection(self, client: "MockChatClient") -> None:
        """Test that changing the order of middleware is detected and applied."""
        execution_log: list[str] = []

        middleware1 = self.TrackingAgentMiddleware("first", execution_log)
        middleware2 = self.TrackingAgentMiddleware("second", execution_log)

        # Create agent with middleware in order [first, second]
        agent = Agent(client=client, middleware=[middleware1, middleware2])

        # First execution
        await agent.run("Test message 1")
        assert execution_log == ["first_start", "second_start", "second_end", "first_end"]

        # Clear execution log
        execution_log.clear()

        # Change order to [second, first]
        agent.middleware = [middleware2, middleware1]

        # Second execution - should reflect new order
        await agent.run("Test message 2")
        assert execution_log == ["second_start", "first_start", "first_end", "second_end"]


class TestRunLevelMiddleware:
    """Test cases for run-level middleware functionality."""

    class TrackingAgentMiddleware(AgentMiddleware):
        """Test middleware that tracks execution."""

        def __init__(self, name: str, execution_log: list[str]):
            self.name = name
            self.execution_log = execution_log

        async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            self.execution_log.append(f"{self.name}_start")
            await call_next()
            self.execution_log.append(f"{self.name}_end")

    async def test_run_level_middleware_isolation(self, client: "MockChatClient") -> None:
        """Test that run-level middleware is isolated between multiple runs."""
        execution_log: list[str] = []

        # Create agent without any agent-level middleware
        agent = Agent(client=client)

        # Create run-level middleware
        run_middleware1 = self.TrackingAgentMiddleware("run1", execution_log)
        run_middleware2 = self.TrackingAgentMiddleware("run2", execution_log)

        # First run with run_middleware1
        await agent.run("Test message 1", middleware=[run_middleware1])
        assert execution_log == ["run1_start", "run1_end"]

        # Clear execution log
        execution_log.clear()

        # Second run with run_middleware2 - should not see run_middleware1
        await agent.run("Test message 2", middleware=[run_middleware2])
        assert execution_log == ["run2_start", "run2_end"]
        assert "run1_start" not in execution_log
        assert "run1_end" not in execution_log

        # Clear execution log
        execution_log.clear()

        # Third run with no middleware - should not see any middleware execution
        await agent.run("Test message 3")
        assert execution_log == []

        # Clear execution log
        execution_log.clear()

        # Fourth run with both run middleware - should see both
        await agent.run("Test message 4", middleware=[run_middleware1, run_middleware2])
        assert execution_log == ["run1_start", "run2_start", "run2_end", "run1_end"]

    async def test_agent_plus_run_middleware_execution_order(self, client: "MockChatClient") -> None:
        """Test that agent middleware executes first, followed by run middleware."""
        execution_log: list[str] = []
        metadata_log: list[str] = []

        class MetadataAgentMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_log.append(f"{self.name}_start")
                # Set metadata to pass information to run middleware
                context.metadata[f"{self.name}_key"] = f"{self.name}_value"
                await call_next()
                execution_log.append(f"{self.name}_end")

        class MetadataRunMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_log.append(f"{self.name}_start")
                # Read metadata set by agent middleware
                for key, value in context.metadata.items():
                    metadata_log.append(f"{self.name}_reads_{key}:{value}")
                # Set run-level metadata
                context.metadata[f"{self.name}_key"] = f"{self.name}_value"
                await call_next()
                execution_log.append(f"{self.name}_end")

        # Create agent with agent-level middleware
        agent_middleware = MetadataAgentMiddleware("agent")
        agent = Agent(client=client, middleware=[agent_middleware])

        # Create run-level middleware
        run_middleware = MetadataRunMiddleware("run")

        # Execute with both agent and run middleware
        await agent.run("Test message", middleware=[run_middleware])

        # Verify execution order: agent middleware wraps run middleware
        expected_order = ["agent_start", "run_start", "run_end", "agent_end"]
        assert execution_log == expected_order

        # Verify that run middleware can read agent middleware metadata
        assert "run_reads_agent_key:agent_value" in metadata_log

    async def test_run_level_middleware_non_streaming(self, client: "MockChatClient") -> None:
        """Test run-level middleware with non-streaming execution."""
        execution_log: list[str] = []

        # Create agent without agent-level middleware
        agent = Agent(client=client)

        # Create run-level middleware
        run_middleware = self.TrackingAgentMiddleware("run_nonstream", execution_log)

        # Execute non-streaming with run middleware
        response = await agent.run("Test non-streaming", middleware=[run_middleware])

        # Verify response is correct
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"
        assert "test response" in response.messages[0].text

        # Verify middleware was executed
        assert execution_log == ["run_nonstream_start", "run_nonstream_end"]

    async def test_run_level_middleware_streaming(self, client: "MockChatClient") -> None:
        """Test run-level middleware with streaming execution."""
        execution_log: list[str] = []
        streaming_flags: list[bool] = []

        class StreamingTrackingMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_log.append(f"{self.name}_start")
                streaming_flags.append(context.stream)
                await call_next()
                execution_log.append(f"{self.name}_end")

        # Create agent without agent-level middleware
        agent = Agent(client=client)

        # Set up mock streaming responses
        client.streaming_responses = [
            [
                ChatResponseUpdate(contents=[Content.from_text(text="Stream")], role="assistant"),
                ChatResponseUpdate(contents=[Content.from_text(text=" response")], role="assistant"),
            ]
        ]

        # Create run-level middleware
        run_middleware = StreamingTrackingMiddleware("run_stream")

        # Execute streaming with run middleware
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Test streaming", middleware=[run_middleware], stream=True):
            updates.append(update)

        # Verify streaming responsecod
        assert len(updates) == 2
        assert updates[0].text == "Stream"
        assert updates[1].text == " response"

        # Verify middleware was executed with correct streaming flag
        assert execution_log == ["run_stream_start", "run_stream_end"]
        assert streaming_flags == [True]  # Context should indicate streaming

    async def test_agent_and_run_level_both_agent_and_function_middleware(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test complete scenario with agent and function middleware at both agent-level and run-level."""
        execution_log: list[str] = []

        # Agent-level middleware
        class AgentLevelAgentMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_log.append("agent_level_agent_start")
                context.metadata["agent_level_agent"] = "processed"
                await call_next()
                execution_log.append("agent_level_agent_end")

        class AgentLevelFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_log.append("agent_level_function_start")
                context.metadata["agent_level_function"] = "processed"
                await call_next()
                execution_log.append("agent_level_function_end")

        # Run-level middleware
        class RunLevelAgentMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_log.append("run_level_agent_start")
                # Verify agent-level middleware metadata is available
                assert "agent_level_agent" in context.metadata
                context.metadata["run_level_agent"] = "processed"
                await call_next()
                execution_log.append("run_level_agent_end")

        class RunLevelFunctionMiddleware(FunctionMiddleware):
            async def process(
                self,
                context: FunctionInvocationContext,
                call_next: Callable[[], Awaitable[None]],
            ) -> None:
                execution_log.append("run_level_function_start")
                # Verify agent-level function middleware metadata is available
                assert "agent_level_function" in context.metadata
                context.metadata["run_level_function"] = "processed"
                await call_next()
                execution_log.append("run_level_function_end")

        # Create tool function for testing function middleware
        def custom_tool(message: str) -> str:
            execution_log.append("tool_executed")
            return f"Tool response: {message}"

        custom_tool_wrapped = FunctionTool(
            func=custom_tool, name="custom_tool", description="Custom tool", approval_mode="never_require"
        )

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="test_call",
                            name="custom_tool",
                            arguments='{"message": "test"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])
        chat_client_base.run_responses = [function_call_response, final_response]

        # Create agent with agent-level middleware
        agent = Agent(
            client=chat_client_base,
            middleware=[AgentLevelAgentMiddleware(), AgentLevelFunctionMiddleware()],
            tools=[custom_tool_wrapped],
        )

        # Execute with run-level middleware
        response = await agent.run(
            "Test message",
            middleware=[RunLevelAgentMiddleware(), RunLevelFunctionMiddleware()],
        )

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client_base.call_count == 2  # Function call + final response

        expected_order = [
            "agent_level_agent_start",
            "run_level_agent_start",
            "agent_level_function_start",
            "run_level_function_start",
            "tool_executed",
            "run_level_function_end",
            "agent_level_function_end",
            "run_level_agent_end",
            "agent_level_agent_end",
        ]
        assert execution_log == expected_order

        # Verify function call and result are in the response
        all_contents = [content for message in response.messages for content in message.contents]
        function_calls = [c for c in all_contents if c.type == "function_call"]
        function_results = [c for c in all_contents if c.type == "function_result"]

        assert len(function_calls) == 1
        assert len(function_results) == 1
        assert function_calls[0].name == "custom_tool"
        assert function_results[0].call_id == function_calls[0].call_id
        assert function_results[0].result is not None
        assert "Tool response: test" in str(function_results[0].result)


class TestMiddlewareDecoratorLogic:
    """Test the middleware decorator and type annotation logic."""

    async def test_decorator_and_type_match(self, chat_client_base: "MockBaseChatClient") -> None:
        """Both decorator and parameter type specified and match."""

        execution_order: list[str] = []

        @agent_middleware
        async def matching_agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("decorator_type_match_agent")
            await call_next()

        @function_middleware
        async def matching_function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("decorator_type_match_function")
            await call_next()

        # Create tool function for testing function middleware
        def custom_tool(message: str) -> str:
            execution_order.append("tool_executed")
            return f"Tool response: {message}"

        custom_tool_wrapped = FunctionTool(
            func=custom_tool, name="custom_tool", description="Custom tool", approval_mode="never_require"
        )

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="test_call",
                            name="custom_tool",
                            arguments='{"message": "test"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])
        chat_client_base.responses = [function_call_response, final_response]

        # Should work without errors
        agent = Agent(
            client=chat_client_base,
            middleware=[matching_agent_middleware, matching_function_middleware],
            tools=[custom_tool_wrapped],
        )

        response = await agent.run([Message(role="user", text="test")])

        assert response is not None
        assert "decorator_type_match_agent" in execution_order
        assert "decorator_type_match_function" not in execution_order

    async def test_decorator_and_type_mismatch(self, client: MockChatClient) -> None:
        """Both decorator and parameter type specified but don't match."""

        # This will cause a type error at decoration time, so we need to test differently
        # Should raise MiddlewareException due to mismatch during agent creation
        with pytest.raises(MiddlewareException, match="MiddlewareTypes type mismatch"):

            @agent_middleware  # type: ignore[arg-type]
            async def mismatched_middleware(
                context: FunctionInvocationContext,  # Wrong type for @agent_middleware
                call_next: Any,
            ) -> None:
                await call_next()

            agent = Agent(client=client, middleware=[mismatched_middleware])
            await agent.run([Message(role="user", text="test")])

    async def test_only_decorator_specified(self, chat_client_base: "MockBaseChatClient") -> None:
        """Only decorator specified - rely on decorator."""
        execution_order: list[str] = []

        @agent_middleware
        async def decorator_only_agent(context: Any, call_next: Any) -> None:  # No type annotation
            execution_order.append("decorator_only_agent")
            await call_next()

        @function_middleware
        async def decorator_only_function(context: Any, call_next: Any) -> None:  # No type annotation
            execution_order.append("decorator_only_function")
            await call_next()

        # Create tool function for testing function middleware
        def custom_tool(message: str) -> str:
            execution_order.append("tool_executed")
            return f"Tool response: {message}"

        custom_tool_wrapped = FunctionTool(
            func=custom_tool, name="custom_tool", description="Custom tool", approval_mode="never_require"
        )

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="test_call",
                            name="custom_tool",
                            arguments='{"message": "test"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])
        chat_client_base.responses = [function_call_response, final_response]

        # Should work - relies on decorator
        agent = Agent(
            client=chat_client_base,
            middleware=[decorator_only_agent, decorator_only_function],
            tools=[custom_tool_wrapped],
        )

        response = await agent.run([Message(role="user", text="test")])

        assert response is not None
        assert "decorator_only_agent" in execution_order
        assert "decorator_only_function" not in execution_order

    async def test_only_type_specified(self, chat_client_base: "MockBaseChatClient") -> None:
        """Only parameter type specified - rely on types."""
        execution_order: list[str] = []

        # No decorator
        async def type_only_agent(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("type_only_agent")
            await call_next()

        # No decorator
        async def type_only_function(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("type_only_function")
            await call_next()

        # Create tool function for testing function middleware
        def custom_tool(message: str) -> str:
            execution_order.append("tool_executed")
            return f"Tool response: {message}"

        custom_tool_wrapped = FunctionTool(
            func=custom_tool, name="custom_tool", description="Custom tool", approval_mode="never_require"
        )

        # Set up mock to return a function call first, then a regular response
        function_call_response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="test_call",
                            name="custom_tool",
                            arguments='{"message": "test"}',
                        )
                    ],
                )
            ]
        )
        final_response = ChatResponse(messages=[Message(role="assistant", text="Final response")])
        chat_client_base.responses = [function_call_response, final_response]

        # Should work - relies on type annotations
        agent = Agent(
            client=chat_client_base, middleware=[type_only_agent, type_only_function], tools=[custom_tool_wrapped]
        )

        response = await agent.run([Message(role="user", text="test")])

        assert response is not None
        assert "type_only_agent" in execution_order
        assert "type_only_function" not in execution_order

    async def test_neither_decorator_nor_type(self, client: Any) -> None:
        """Neither decorator nor parameter type specified - should throw exception."""

        async def no_info_middleware(context: Any, call_next: Any) -> None:  # No decorator, no type
            await call_next()

        # Should raise MiddlewareException
        with pytest.raises(MiddlewareException, match="Cannot determine middleware type"):
            agent = Agent(client=client, middleware=[no_info_middleware])
            await agent.run([Message(role="user", text="test")])

    async def test_insufficient_parameters_error(self, client: Any) -> None:
        """Test that middleware with insufficient parameters raises an error."""
        from agent_framework import Agent, agent_middleware

        # Should raise MiddlewareException about insufficient parameters
        with pytest.raises(MiddlewareException, match="must have at least 2 parameters"):

            @agent_middleware  # type: ignore[arg-type]
            async def insufficient_params_middleware(context: Any) -> None:  # Missing 'next' parameter
                pass

            agent = Agent(client=client, middleware=[insufficient_params_middleware])
            await agent.run([Message(role="user", text="test")])

    async def test_decorator_markers_preserved(self) -> None:
        """Test that decorator markers are properly set on functions."""

        @agent_middleware
        async def test_agent_middleware(context: Any, call_next: Any) -> None:
            pass

        @function_middleware
        async def test_function_middleware(context: Any, call_next: Any) -> None:
            pass

        # Check that decorator markers were set
        assert hasattr(test_agent_middleware, "_middleware_type")
        assert test_agent_middleware._middleware_type == MiddlewareType.AGENT  # type: ignore[attr-defined]

        assert hasattr(test_function_middleware, "_middleware_type")
        assert test_function_middleware._middleware_type == MiddlewareType.FUNCTION  # type: ignore[attr-defined]


class TestChatAgentSessionBehavior:
    """Test cases for session behavior in AgentContext across multiple runs."""

    async def test_agent_context_session_behavior_across_multiple_runs(self, client: "MockChatClient") -> None:
        """Test that AgentContext.session property behaves correctly across multiple agent runs."""
        thread_states: list[dict[str, Any]] = []

        class SessionTrackingMiddleware(AgentMiddleware):
            async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
                # Capture state before next() call
                thread_messages = []
                if context.session and context.session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID):
                    thread_messages = context.session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {}).get(
                        "messages", []
                    )

                before_state = {
                    "before_next": True,
                    "messages_count": len(context.messages),
                    "thread_count": len(thread_messages),
                    "messages_text": [msg.text for msg in context.messages if msg.text],
                    "thread_messages_text": [msg.text for msg in thread_messages if msg.text],
                }
                thread_states.append(before_state)

                await call_next()

                # Capture state after next() call
                thread_messages_after = []
                if context.session and context.session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID):
                    thread_messages_after = context.session.state.get(
                        InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {}
                    ).get("messages", [])

                after_state = {
                    "before_next": False,
                    "messages_count": len(context.messages),
                    "thread_count": len(thread_messages_after),
                    "messages_text": [msg.text for msg in context.messages if msg.text],
                    "thread_messages_text": [msg.text for msg in thread_messages_after if msg.text],
                }
                thread_states.append(after_state)

        # Create Agent with session tracking middleware
        middleware = SessionTrackingMiddleware()
        agent = Agent(client=client, middleware=[middleware])

        # Create a session that will persist messages between runs
        session = agent.create_session()

        # First run
        first_messages = [Message(role="user", text="first message")]
        first_response = await agent.run(first_messages, session=session)

        # Verify first response
        assert first_response is not None
        assert len(first_response.messages) > 0

        # Second run - use the same thread
        second_messages = [Message(role="user", text="second message")]
        second_response = await agent.run(second_messages, session=session)

        # Verify second response
        assert second_response is not None
        assert len(second_response.messages) > 0

        # Verify we captured states for both runs (before and after next() for each)
        assert len(thread_states) == 4

        # First run - before next()
        first_before = thread_states[0]
        assert first_before["before_next"] is True
        assert first_before["messages_count"] == 1
        assert first_before["thread_count"] == 0  # Thread is empty before first run
        assert first_before["messages_text"] == ["first message"]
        assert first_before["thread_messages_text"] == []

        # First run - after next()
        first_after = thread_states[1]
        assert first_after["before_next"] is False
        assert first_after["messages_count"] == 1  # Input messages unchanged
        assert first_after["thread_count"] == 2  # Input + response
        assert first_after["messages_text"] == ["first message"]
        # Thread should contain input + response
        assert "first message" in first_after["thread_messages_text"]
        assert "test response" in " ".join(first_after["thread_messages_text"])

        # Second run - before next()
        second_before = thread_states[2]
        assert second_before["before_next"] is True
        assert second_before["messages_count"] == 1  # Only current run input
        assert second_before["thread_count"] == 2  # Previous run history (input + response)
        assert second_before["messages_text"] == ["second message"]
        # Thread should contain previous run history but not current input yet
        assert "first message" in second_before["thread_messages_text"]
        assert "test response" in " ".join(second_before["thread_messages_text"])
        assert "second message" not in second_before["thread_messages_text"]

        # Second run - after next()
        second_after = thread_states[3]
        assert second_after["before_next"] is False
        assert second_after["messages_count"] == 1  # Input messages unchanged
        assert second_after["thread_count"] == 4  # Previous history + current input + current response
        assert second_after["messages_text"] == ["second message"]
        # Thread should contain: first input + first response + second input + second response
        assert "first message" in second_after["thread_messages_text"]
        assert "second message" in second_after["thread_messages_text"]
        # Should have two "test response" entries (one for each run)
        response_count = sum(1 for text in second_after["thread_messages_text"] if "test response" in text)
        assert response_count == 2


class TestChatAgentChatMiddleware:
    """Test cases for chat middleware integration with Agent."""

    async def test_class_based_chat_middleware_with_chat_agent(self) -> None:
        """Test class-based chat middleware with Agent."""
        execution_order: list[str] = []

        class TrackingChatMiddleware(ChatMiddleware):
            async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("chat_middleware_before")
                await call_next()
                execution_order.append("chat_middleware_after")

        # Create Agent with chat middleware
        client = MockBaseChatClient()
        middleware = TrackingChatMiddleware()
        agent = Agent(client=client, middleware=[middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"
        assert "test response" in response.messages[0].text
        assert execution_order == [
            "chat_middleware_before",
            "chat_middleware_after",
        ]

    async def test_function_based_chat_middleware_with_chat_agent(self) -> None:
        """Test function-based chat middleware with Agent."""
        execution_order: list[str] = []

        async def tracking_chat_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("chat_middleware_before")
            await call_next()
            execution_order.append("chat_middleware_after")

        # Create Agent with function-based chat middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[tracking_chat_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == "assistant"
        assert "test response" in response.messages[0].text
        assert execution_order == [
            "chat_middleware_before",
            "chat_middleware_after",
        ]

    async def test_chat_middleware_can_modify_messages(self) -> None:
        """Test that chat middleware can modify messages before sending to model."""

        @chat_middleware
        async def message_modifier_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            # Modify the first message by adding a prefix
            if context.messages:
                for idx, msg in enumerate(context.messages):
                    if msg.role == "system":
                        continue
                    original_text = msg.text or ""
                    context.messages[idx] = Message(role=msg.role, text=f"MODIFIED: {original_text}")
                    break
            await call_next()

        # Create Agent with message-modifying middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[message_modifier_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify that the message was modified (MockBaseChatClient echoes back the input)
        assert response and response.messages
        assert "MODIFIED: test message" in response.messages[0].text

    async def test_chat_middleware_can_override_response(self) -> None:
        """Test that chat middleware can override the response."""

        @chat_middleware
        async def response_override_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            # Override the response without calling next()
            context.result = ChatResponse(
                messages=[Message(role="assistant", text="MiddlewareTypes overridden response")],
                response_id="middleware-response-123",
            )
            context.terminate = True

        # Create Agent with response-overriding middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[response_override_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify that the response was overridden
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].text == "MiddlewareTypes overridden response"
        assert response.response_id == "middleware-response-123"

    async def test_multiple_chat_middleware_execution_order(self) -> None:
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

        # Create Agent with multiple chat middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[first_middleware, second_middleware])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert execution_order == [
            "first_before",
            "second_before",
            "second_after",
            "first_after",
        ]

    async def test_chat_middleware_with_streaming(self) -> None:
        """Test chat middleware with streaming responses."""
        execution_order: list[str] = []
        streaming_flags: list[bool] = []

        class StreamingTrackingChatMiddleware(ChatMiddleware):
            async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("streaming_chat_before")
                streaming_flags.append(context.stream)
                await call_next()
                execution_order.append("streaming_chat_after")

        # Create Agent with chat middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[StreamingTrackingChatMiddleware()])

        # Set up mock streaming responses
        # TODO: refactor to return a ResponseStream object
        client.streaming_responses = [
            [
                ChatResponseUpdate(contents=[Content.from_text(text="Stream")], role="assistant"),
                ChatResponseUpdate(contents=[Content.from_text(text=" response")], role="assistant"),
            ]
        ]

        # Execute streaming
        messages = [Message(role="user", text="test message")]
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run(messages, stream=True):
            updates.append(update)

        # Verify streaming response
        assert len(updates) >= 1  # At least some updates
        assert execution_order == [
            "streaming_chat_before",
            "streaming_chat_after",
        ]

        # Verify streaming flag was set (at least one True)
        assert True in streaming_flags

    async def test_chat_middleware_termination_before_execution(self) -> None:
        """Test that chat middleware can terminate execution before calling next()."""
        execution_order: list[str] = []

        class PreTerminationChatMiddleware(ChatMiddleware):
            async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("middleware_before")
                # Set a custom response since we're terminating
                context.result = ChatResponse(messages=[Message(role="assistant", text="Terminated by middleware")])
                raise MiddlewareTermination
                # We call next() but since terminate=True, execution should stop
                await call_next()
                execution_order.append("middleware_after")

        # Create Agent with terminating middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[PreTerminationChatMiddleware()])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response was from middleware
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].text == "Terminated by middleware"
        assert execution_order == ["middleware_before"]

    async def test_chat_middleware_termination_after_execution(self) -> None:
        """Test that chat middleware can terminate execution after calling next()."""
        execution_order: list[str] = []

        class PostTerminationChatMiddleware(ChatMiddleware):
            async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
                execution_order.append("middleware_before")
                await call_next()
                execution_order.append("middleware_after")
                context.terminate = True

        # Create Agent with terminating middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[PostTerminationChatMiddleware()])

        # Execute the agent
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages)

        # Verify response is from actual execution
        assert response is not None
        assert len(response.messages) > 0
        assert "test response" in response.messages[0].text
        assert execution_order == [
            "middleware_before",
            "middleware_after",
        ]

    async def test_combined_middleware(self) -> None:
        """Test Agent with combined middleware types."""
        execution_order: list[str] = []

        async def agent_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("agent_middleware_before")
            await call_next()
            execution_order.append("agent_middleware_after")

        async def chat_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
            execution_order.append("chat_middleware_before")
            await call_next()
            execution_order.append("chat_middleware_after")

        async def function_middleware(
            context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            execution_order.append("function_middleware_before")
            await call_next()
            execution_order.append("function_middleware_after")

        # Create Agent with function middleware and tools
        agent = Agent(
            client=MockBaseChatClient(),
            middleware=[chat_middleware, function_middleware, agent_middleware],
            tools=[sample_tool_function],
        )
        await agent.run([Message(role="user", text="test")])

        assert execution_order == [
            "agent_middleware_before",
            "chat_middleware_before",
            "chat_middleware_after",
            "agent_middleware_after",
        ]

    async def test_agent_middleware_can_access_and_override_custom_kwargs(self) -> None:
        """Test that agent middleware can access and override custom parameters like temperature."""
        captured_kwargs: dict[str, Any] = {}
        modified_kwargs: dict[str, Any] = {}

        @agent_middleware
        async def kwargs_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
            # Capture the original kwargs
            captured_kwargs.update(context.kwargs)

            # Modify some kwargs
            context.kwargs["temperature"] = 0.9
            context.kwargs["max_tokens"] = 500
            context.kwargs["new_param"] = "added_by_middleware"

            # Store modified kwargs for verification
            modified_kwargs.update(context.kwargs)

            await call_next()

        # Create Agent with agent middleware
        client = MockBaseChatClient()
        agent = Agent(client=client, middleware=[kwargs_middleware])

        # Execute the agent with custom parameters
        messages = [Message(role="user", text="test message")]
        response = await agent.run(messages, temperature=0.7, max_tokens=100, custom_param="test_value")

        # Verify response
        assert response is not None
        assert len(response.messages) > 0

        # Verify middleware captured the original kwargs
        assert captured_kwargs["temperature"] == 0.7
        assert captured_kwargs["max_tokens"] == 100
        assert captured_kwargs["custom_param"] == "test_value"

        # Verify middleware could modify the kwargs
        assert modified_kwargs["temperature"] == 0.9
        assert modified_kwargs["max_tokens"] == 500
        assert modified_kwargs["new_param"] == "added_by_middleware"
        assert modified_kwargs["custom_param"] == "test_value"  # Should still be there


# class TestMiddlewareWithProtocolOnlyAgent:
#     """Test use_agent_middleware with agents implementing only SupportsAgentRun."""

# async def test_middleware_with_protocol_only_agent(self) -> None:
#     """Verify middleware works without BaseAgent inheritance for both run."""
#     from collections.abc import AsyncIterable

#     from agent_framework import SupportsAgentRun, AgentResponse, AgentResponseUpdate

#     execution_order: list[str] = []

#     class TrackingMiddleware(AgentMiddleware):
#         async def process(
#             self, context: AgentContext, call_next: Callable[[], Awaitable[None]]
#         ) -> None:
#             execution_order.append("before")
#             await call_next()
#             execution_order.append("after")

#     @use_agent_middleware
#     class ProtocolOnlyAgent:
#         """Minimal agent implementing only SupportsAgentRun, not inheriting from BaseAgent."""

#         def __init__(self):
#             self.id = "protocol-only-agent"
#             self.name = "Protocol Only Agent"
#             self.description = "Test agent"
#             self.middleware = [TrackingMiddleware()]

#         async def run(
#             self, messages=None, *, stream: bool = False, thread=None, **kwargs
#         ) -> AgentResponse | AsyncIterable[AgentResponseUpdate]:
#             if stream:

#                 async def _stream():
#                     yield AgentResponseUpdate()

#                 return _stream()
#             return AgentResponse(messages=[Message(role="assistant", text="response")])

#         def get_new_thread(self, **kwargs):
#             return None

#     agent = ProtocolOnlyAgent()
#     assert isinstance(agent, SupportsAgentRun)

#     # Test run (non-streaming)
#     response = await agent.run("test message")
#     assert response is not None
#     assert execution_order == ["before", "after"]
