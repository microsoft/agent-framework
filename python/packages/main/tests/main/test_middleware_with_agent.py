# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable, Callable

from agent_framework import (
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
from agent_framework._middleware import (
    AgentMiddleware,
    AgentRunContext,
    FunctionInvocationContext,
    FunctionMiddleware,
)

from .conftest import MockChatClient

# region ChatAgent Tests


class TestChatAgentClassBasedMiddleware:
    """Test cases for class-based middleware integration with ChatAgent."""

    async def test_class_based_agent_middleware_with_chat_agent(self, chat_client: "MockChatClient") -> None:
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
        agent = ChatAgent(chat_client=chat_client, middleware=[middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == Role.ASSISTANT
        # Note: conftest "MockChatClient" returns different text format
        assert "test response" in response.messages[0].text

        # Verify middleware execution order
        assert execution_order == ["agent_middleware_before", "agent_middleware_after"]

    async def test_class_based_function_middleware_with_chat_agent(self, chat_client: "MockChatClient") -> None:
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
        agent = ChatAgent(chat_client=chat_client, middleware=[middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client.call_count == 1

        # Note: Function middleware won't execute since no function calls are made
        assert execution_order == []


class TestChatAgentFunctionBasedMiddleware:
    """Test cases for function-based middleware integration with ChatAgent."""

    async def test_function_based_agent_middleware_with_chat_agent(self, chat_client: "MockChatClient") -> None:
        """Test function-based agent middleware with ChatAgent."""
        execution_order: list[str] = []

        async def tracking_agent_middleware(
            context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
        ) -> None:
            execution_order.append("agent_function_before")
            await next(context)
            execution_order.append("agent_function_after")

        # Create ChatAgent with function middleware
        agent = ChatAgent(chat_client=chat_client, middleware=[tracking_agent_middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert response.messages[0].role == Role.ASSISTANT
        assert response.messages[0].text == "test response"
        assert chat_client.call_count == 1

        # Verify middleware execution order
        assert execution_order == ["agent_function_before", "agent_function_after"]

    async def test_function_based_function_middleware_with_chat_agent(self, chat_client: "MockChatClient") -> None:
        """Test function-based function middleware with ChatAgent."""
        execution_order: list[str] = []

        async def tracking_function_middleware(
            context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
        ) -> None:
            execution_order.append("function_function_before")
            await next(context)
            execution_order.append("function_function_after")

        # Create ChatAgent with function middleware (no tools, so function middleware won't be triggered)
        agent = ChatAgent(chat_client=chat_client, middleware=[tracking_function_middleware])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client.call_count == 1

        # Note: Function middleware won't execute since no function calls are made
        assert execution_order == []


class TestChatAgentStreamingMiddleware:
    """Test cases for streaming middleware integration with ChatAgent."""

    async def test_agent_middleware_with_streaming(self, chat_client: "MockChatClient") -> None:
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
        agent = ChatAgent(chat_client=chat_client, middleware=[middleware])

        # Set up mock streaming responses
        chat_client.streaming_responses = [
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
        assert chat_client.call_count == 1

        # Verify middleware was called and streaming flag was set correctly
        assert execution_order == ["middleware_before", "middleware_after"]
        assert streaming_flags == [True]  # Context should indicate streaming

    async def test_non_streaming_vs_streaming_flag_validation(self, chat_client: "MockChatClient") -> None:
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
        agent = ChatAgent(chat_client=chat_client, middleware=[middleware])
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

    async def test_multiple_agent_middleware_execution_order(self, chat_client: "MockChatClient") -> None:
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
        agent = ChatAgent(chat_client=chat_client, middleware=[middleware1, middleware2, middleware3])

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="test message")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert chat_client.call_count == 1

        # Verify execution order (should be nested: first wraps second wraps third)
        expected_order = ["first_before", "second_before", "third_before", "third_after", "second_after", "first_after"]
        assert execution_order == expected_order

    async def test_mixed_middleware_types_with_chat_agent(self, chat_client: "MockChatClient") -> None:
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
            chat_client=chat_client,
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
        assert chat_client.call_count == 1

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

    async def test_class_based_function_middleware_with_tool_calls(self, chat_client: "MockChatClient") -> None:
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

        chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with function middleware and tools
        middleware = TrackingFunctionMiddleware("function_middleware")
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for Seattle")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client.call_count == 2  # Two calls: one for function call, one for final response

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

    async def test_function_based_function_middleware_with_tool_calls(self, chat_client: "MockChatClient") -> None:
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

        chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with function middleware and tools
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[tracking_function_middleware],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for San Francisco")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client.call_count == 2  # Two calls: one for function call, one for final response

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

    async def test_mixed_agent_and_function_middleware_with_tool_calls(self, chat_client: "MockChatClient") -> None:
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

        chat_client.responses = [function_call_response, final_response]

        # Create ChatAgent with both agent and function middleware and tools
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[TrackingAgentMiddleware(), TrackingFunctionMiddleware()],
            tools=[sample_tool_function],
        )

        # Execute the agent
        messages = [ChatMessage(role=Role.USER, text="Get weather for New York")]
        response = await agent.run(messages)

        # Verify response
        assert response is not None
        assert len(response.messages) > 0
        assert chat_client.call_count == 2  # Two calls: one for function call, one for final response

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
