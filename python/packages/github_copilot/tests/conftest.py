# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable, Mapping, Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ContextProvider,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    FunctionMiddleware,
    FunctionTool,
    Message,
    MiddlewareBundle,
    MiddlewareTypes,
    ResponseStream,
    SessionContext,
    function_middleware,
    tool,
)
from copilot.session_events import SessionEvent


@pytest.fixture
def completed_copilot_session(
    mock_session: MagicMock,
    assistant_message_event: SessionEvent,
    session_idle_event: SessionEvent,
) -> MagicMock:
    mock_session.send_and_wait.return_value = assistant_message_event

    def subscribe(handler: Callable[[SessionEvent], None]) -> Callable[[], None]:
        handler(session_idle_event)
        return lambda: None

    mock_session.on.side_effect = subscribe
    return mock_session


@pytest.fixture(params=["class", "decorated", "annotated", "bundle"])
def provider_function_middleware(
    request: pytest.FixtureRequest,
) -> tuple[ContextProvider, FunctionTool, AsyncMock, AsyncMock]:
    tool_body = AsyncMock()
    policy = AsyncMock(side_effect=RuntimeError("Function policy denied the call"))

    @tool(approval_mode="never_require")
    async def provider_tool(value: str) -> str:
        """Return the supplied value."""
        await tool_body(value)
        return value

    async def deny_call(
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        await policy(context)

    class DenyMiddleware(FunctionMiddleware):
        async def process(
            self,
            context: FunctionInvocationContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            await policy(context)

    middleware: MiddlewareTypes
    if request.param == "class":
        middleware = DenyMiddleware()
    elif request.param == "decorated":
        middleware = function_middleware(deny_call)
    elif request.param == "annotated":
        middleware = deny_call
    else:
        middleware = MiddlewareBundle([deny_call])

    class ToolProvider(ContextProvider):
        async def before_run(
            self,
            *,
            agent: Any,
            session: Any,
            context: SessionContext,
            state: dict[str, Any],
        ) -> None:
            context.extend_tools(self.source_id, [provider_tool])
            if state.get("include_middleware", True):
                context.extend_middleware(self.source_id, middleware)

    return ToolProvider(source_id="tool-policy"), provider_tool, tool_body, policy


@pytest.fixture
def tool_calling_chat_client(
    provider_function_middleware: tuple[ContextProvider, FunctionTool, AsyncMock, AsyncMock],
) -> BaseChatClient[ChatOptions[Any]]:
    _, provider_tool, _, _ = provider_function_middleware

    class ToolCallingClient(FunctionInvocationLayer[ChatOptions[Any]], BaseChatClient[ChatOptions[Any]]):
        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            has_result = any(content.type == "function_result" for message in messages for content in message.contents)
            contents = (
                [Content.from_text("Done")]
                if has_result
                else [
                    Content.from_function_call(
                        call_id="provider-call",
                        name=provider_tool.name,
                        arguments={"value": "test"},
                    )
                ]
            )

            if stream:

                async def updates() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(
                        role="assistant",
                        contents=contents,
                        finish_reason="stop" if has_result else "tool_calls",
                    )

                return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

            async def response() -> ChatResponse:
                return ChatResponse(messages=[Message(role="assistant", contents=contents)])

            return response()

    return ToolCallingClient()
