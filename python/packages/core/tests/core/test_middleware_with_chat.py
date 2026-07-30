# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any, cast
from unittest.mock import patch

import pytest

from agent_framework import (
    MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY,
    Agent,
    AgentSession,
    ChatContext,
    ChatMiddleware,
    ChatMiddlewareTypes,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationContext,
    FunctionTool,
    Message,
    MessageInjectionMiddleware,
    ResponseStream,
    SupportsChatGetResponse,
    chat_middleware,
    enqueue_messages,
    function_middleware,
    tool,
)
from agent_framework.exceptions import ChatClientInvalidRequestException

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
        chat_client_base.chat_middleware = [LoggingChatMiddleware()]  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, logging_chat_middleware)]

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
                context.messages[0] = Message(role=context.messages[0].role, contents=[f"MODIFIED: {original_text}"])  # type: ignore[index]  # pyrefly: ignore[unsupported-operation]  # ty: ignore[invalid-assignment]
            await call_next()

        # Add middleware to chat client
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, message_modifier_middleware)]

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
            context.terminate = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        # Add middleware to chat client
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, response_override_middleware)]

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
        chat_client_base.chat_middleware = [
            cast(ChatMiddlewareTypes, first_middleware),
            cast(ChatMiddlewareTypes, second_middleware),
        ]

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
                        content.text = content.text.upper()  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
                return update

            context.stream_transform_hooks.append(upper_case_update)
            await call_next()
            execution_order.append("streaming_after")

        # Add middleware to chat client
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, streaming_middleware)]

        # Execute streaming response
        messages = [Message(role="user", contents=["test message"])]
        updates: list[object] = []
        async for update in chat_client_base.get_response(messages, stream=True):
            updates.append(update)

        # Verify we got updates
        assert len(updates) > 0
        assert all(update.text == update.text.upper() for update in updates)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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

            context.options["temperature"] = 0.9  # ty: ignore[invalid-assignment]
            context.options["max_tokens"] = 500  # ty: ignore[invalid-assignment]
            context.options["new_param"] = "added_by_middleware"  # ty: ignore[invalid-assignment]

            modified_options.update(context.options)

            await call_next()

        # Add middleware to chat client
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, kwargs_middleware)]

        # Execute chat client with runtime options
        messages = [Message(role="user", contents=["test message"])]
        response = await chat_client_base.get_response(  # type: ignore[call-overload, var-annotated]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
            messages,
            options={"temperature": 0.7, "max_tokens": 100, "custom_param": "test_value"},  # type: ignore[typeddict-unknown-key]  # ty: ignore[invalid-key]
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

    async def test_message_injection_middleware_appends_prequeued_messages(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that queued session messages are appended to the next model call."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        enqueue_messages(session, "queued message")
        captured_messages: list[list[str | None]] = []

        async def fake_get_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ChatResponse:
            captured_messages.append([message.text for message in messages])
            return ChatResponse(messages=Message(role="assistant", contents=["ok"]))

        with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
            agent = Agent(client=chat_client_base, middleware=[injection])
            response = await agent.run("user message", session=session)

        assert response.messages[0].text == "ok"
        assert captured_messages == [["user message", "queued message"]]
        assert injection.get_pending_messages(session) == []

    async def test_message_injection_middleware_loops_when_messages_are_queued_after_call(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that queued messages after a non-tool response trigger another model call."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        captured_messages: list[list[str | None]] = []
        captured_conversation_ids: list[str | None] = []

        async def fake_get_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ChatResponse:
            captured_messages.append([message.text for message in messages])
            captured_conversation_ids.append(options.get("conversation_id"))
            if len(captured_messages) == 1:
                enqueue_messages(session, "queued during call")
                return ChatResponse(
                    messages=Message(role="assistant", contents=["first"]),
                    conversation_id="conversation-1",
                )
            return ChatResponse(messages=Message(role="assistant", contents=["second"]))

        with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
            response = await chat_client_base.get_response(
                [Message(role="user", contents=["user message"])],
                client_kwargs={"middleware": [injection], "session": session},
            )

        assert response.messages[0].text == "second"
        assert captured_messages == [["user message"], ["queued during call"]]
        assert captured_conversation_ids == [None, "conversation-1"]

    async def test_message_injection_middleware_ignores_informational_only_function_calls(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that hosted tool transcript calls do not block injected messages."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        captured_messages: list[list[str | None]] = []

        async def fake_get_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ChatResponse:
            captured_messages.append([message.text for message in messages])
            if len(captured_messages) == 1:
                enqueue_messages(session, "queued after hosted tool")
                return ChatResponse(
                    messages=Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="hosted-call",
                                name="hosted_search",
                                arguments={"query": "docs"},
                                informational_only=True,
                            )
                        ],
                    )
                )
            return ChatResponse(messages=Message(role="assistant", contents=["done"]))

        with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
            response = await chat_client_base.get_response(
                [Message(role="user", contents=["user message"])],
                client_kwargs={"middleware": [injection], "session": session},
            )

        assert response.messages[0].text == "done"
        assert captured_messages == [["user message"], ["queued after hosted tool"]]

    async def test_message_injection_middleware_tool_enqueued_messages_wait_for_function_results(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that tool-enqueued messages are injected after function results are available."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        captured_messages: list[list[Message]] = []
        responses = [
            ChatResponse(
                messages=Message(
                    role="assistant",
                    contents=[Content.from_function_call(call_id="call-1", name="inject_message", arguments={})],
                )
            ),
            ChatResponse(messages=Message(role="assistant", contents=["done"])),
        ]

        @tool(approval_mode="never_require")
        def inject_message(ctx: FunctionInvocationContext) -> str:
            """Inject a message into the active session."""
            active_session = ctx.session
            if active_session is None:
                raise AssertionError("Expected an active session.")
            assert active_session is session
            enqueue_messages(active_session, "queued from tool")
            return "tool result"

        async def fake_get_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ChatResponse:
            captured_messages.append(list(messages))
            return responses.pop(0)

        with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
            agent = Agent(client=chat_client_base, middleware=[injection], tools=[inject_message])
            response = await agent.run("user message", session=session)

        second_call_contents = [content for message in captured_messages[1] for content in message.contents]
        assert response.messages[-1].text == "done"
        assert [message.text for message in captured_messages[0]] == ["user message"]
        assert any(content.type == "function_result" for content in second_call_contents)
        assert captured_messages[1][-1].text == "queued from tool"

    async def test_message_injection_middleware_loops_for_streaming_pending_messages(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that queued messages after a streaming response trigger another streaming model call."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        captured_messages: list[list[str | None]] = []

        def fake_streaming_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
            captured_messages.append([message.text for message in messages])

            async def stream() -> AsyncIterable[ChatResponseUpdate]:
                if len(captured_messages) == 1:
                    yield ChatResponseUpdate(contents=[Content.from_text("first")], role="assistant")
                    enqueue_messages(session, "queued while streaming")
                    return
                yield ChatResponseUpdate(contents=[Content.from_text("second")], role="assistant")

            return ResponseStream(
                stream(),
                finalizer=lambda updates: ChatResponse.from_updates(
                    updates,
                    output_format_type=options.get("response_format"),
                ),
            )

        with patch.object(chat_client_base, "_get_streaming_response", side_effect=fake_streaming_response):
            stream = chat_client_base.get_response(
                [Message(role="user", contents=["user message"])],
                stream=True,
                client_kwargs={"middleware": [injection], "session": session},
            )
            updates = [update async for update in stream]

        assert [update.text for update in updates] == ["first", "second"]
        assert captured_messages == [["user message"], ["queued while streaming"]]

    async def test_message_injection_middleware_streaming_ignores_informational_only_function_calls(
        self, chat_client_base: "MockBaseChatClient"
    ) -> None:
        """Test that streamed hosted tool transcript calls do not block injected messages."""
        session = AgentSession()
        injection = MessageInjectionMiddleware()
        captured_messages: list[list[str | None]] = []

        def fake_streaming_response(
            *,
            messages: Sequence[Message],
            options: dict[str, Any],
            **kwargs: Any,
        ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
            captured_messages.append([message.text for message in messages])

            async def stream() -> AsyncIterable[ChatResponseUpdate]:
                if len(captured_messages) == 1:
                    yield ChatResponseUpdate(
                        contents=[
                            Content.from_function_call(
                                call_id="hosted-call",
                                name="hosted_search",
                                arguments={"query": "docs"},
                                informational_only=True,
                            )
                        ],
                        role="assistant",
                    )
                    enqueue_messages(session, "queued while streaming hosted tool")
                    return
                yield ChatResponseUpdate(contents=[Content.from_text("done")], role="assistant")

            return ResponseStream(
                stream(),
                finalizer=lambda updates: ChatResponse.from_updates(
                    updates,
                    output_format_type=options.get("response_format"),
                ),
            )

        with patch.object(chat_client_base, "_get_streaming_response", side_effect=fake_streaming_response):
            stream = chat_client_base.get_response(
                [Message(role="user", contents=["user message"])],
                stream=True,
                client_kwargs={"middleware": [injection], "session": session},
            )
            updates = [update async for update in stream]

        assert [update.text for update in updates] == ["", "done"]
        assert captured_messages == [["user message"], ["queued while streaming hosted tool"]]

    def test_enqueue_messages_uses_session_state_queue(self) -> None:
        """Test that standalone message injection enqueueing stores messages in session state."""
        session = AgentSession()

        enqueue_messages(session, "queued message")

        queued_messages = session.state[MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY]
        assert [message.text for message in queued_messages] == ["queued message"]

    async def test_message_injection_middleware_requires_session(self, chat_client_base: "MockBaseChatClient") -> None:
        """Test that message injection middleware fails clearly without an active session."""
        with pytest.raises(ChatClientInvalidRequestException, match="requires an AgentSession"):
            await chat_client_base.get_response(
                [Message(role="user", contents=["user message"])],
                client_kwargs={"middleware": [MessageInjectionMiddleware()]},
            )

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
        chat_client_base.chat_middleware = [cast(ChatMiddlewareTypes, base_middleware)]
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
