# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
from collections.abc import AsyncIterable, Awaitable, MutableSequence, Sequence
from typing import Any, Generic
from unittest.mock import patch
from uuid import uuid4

from pytest import fixture

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    ResponseStream,
    SupportsAgentRun,
    tool,
)
from agent_framework._clients import OptionsCoT
from agent_framework.observability import ChatTelemetryLayer

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore
else:
    from typing_extensions import override  # type: ignore[import]
# region Chat History

logger = logging.getLogger(__name__)


@fixture(scope="function")
def chat_history() -> list[Message]:
    return []


# region Tools


@fixture
def ai_tool() -> FunctionTool:
    """Returns a generic FunctionTool."""

    @tool
    def generic_tool(name: str) -> str:
        """A generic tool that echoes the name."""
        return f"Hello, {name}"

    return generic_tool


@fixture
def tool_tool() -> FunctionTool:
    """Returns a executable FunctionTool."""

    @tool(approval_mode="never_require")
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function


# region Chat Clients
class MockChatClient:
    """Simple implementation of a chat client."""

    def __init__(self, **kwargs: Any) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.call_count: int = 0
        self.responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []
        super().__init__(**kwargs)

    def get_response(
        self,
        messages: str | Message | list[str] | list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        options = options or {}
        if stream:
            return self._get_streaming_response(messages=messages, options=options, **kwargs)

        async def _get() -> ChatResponse:
            logger.debug(f"Running custom chat client, with: {messages=}, {kwargs=}")
            self.call_count += 1
            if self.responses:
                return self.responses.pop(0)
            return ChatResponse(messages=Message(role="assistant", text="test response"))

        return _get()

    def _get_streaming_response(
        self,
        *,
        messages: str | Message | list[str] | list[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            logger.debug(f"Running custom chat client stream, with: {messages=}, {kwargs=}")
            self.call_count += 1
            if self.streaming_responses:
                for update in self.streaming_responses.pop(0):
                    yield update
            else:
                yield ChatResponseUpdate(contents=[Content.from_text("test streaming response ")], role="assistant")
                yield ChatResponseUpdate(contents=[Content.from_text("another update")], role="assistant")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)


class MockBaseChatClient(
    ChatMiddlewareLayer[OptionsCoT],
    FunctionInvocationLayer[OptionsCoT],
    ChatTelemetryLayer[OptionsCoT],
    BaseChatClient[OptionsCoT],
    Generic[OptionsCoT],
):
    """Mock implementation of a full-featured ChatClient."""

    def __init__(self, **kwargs: Any):
        super().__init__(function_middleware=[], **kwargs)
        self.run_responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []
        self.call_count: int = 0

    @override
    def _inner_get_response(
        self,
        *,
        messages: MutableSequence[Message],
        stream: bool,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Send a chat request to the AI service.

        Args:
            messages: The chat messages to send.
            stream: Whether to stream the response.
            options: The options dict for the request.
            kwargs: Any additional keyword arguments.

        Returns:
            The chat response or ResponseStream.
        """
        if stream:
            return self._get_streaming_response(messages=messages, options=options, **kwargs)

        async def _get() -> ChatResponse:
            return await self._get_non_streaming_response(messages=messages, options=options, **kwargs)

        return _get()

    async def _get_non_streaming_response(
        self,
        *,
        messages: MutableSequence[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a non-streaming response."""
        logger.debug(f"Running base chat client inner, with: {messages=}, {options=}, {kwargs=}")
        self.call_count += 1
        if not self.run_responses:
            return ChatResponse(messages=Message(role="assistant", text=f"test response - {messages[-1].text}"))

        response = self.run_responses.pop(0)

        if options.get("tool_choice") == "none":
            return ChatResponse(
                messages=Message(
                    role="assistant",
                    text="I broke out of the function invocation loop...",
                ),
                conversation_id=response.conversation_id,
            )

        return response

    def _get_streaming_response(
        self,
        *,
        messages: MutableSequence[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Get a streaming response."""

        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            logger.debug(f"Running base chat client inner stream, with: {messages=}, {options=}, {kwargs=}")
            self.call_count += 1
            if not self.streaming_responses:
                yield ChatResponseUpdate(
                    contents=[Content.from_text(f"update - {messages[0].text}")], role="assistant", finish_reason="stop"
                )
                return
            if options.get("tool_choice") == "none":
                yield ChatResponseUpdate(
                    contents=[Content.from_text("I broke out of the function invocation loop...")],
                    role="assistant",
                    finish_reason="stop",
                )
                return
            response = self.streaming_responses.pop(0)
            for update in response:
                yield update
            await asyncio.sleep(0)

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)


@fixture
def enable_function_calling(request: Any) -> bool:
    return request.param if hasattr(request, "param") else True


@fixture
def max_iterations(request: Any) -> int:
    return request.param if hasattr(request, "param") else 2


@fixture
def client(enable_function_calling: bool, max_iterations: int) -> MockChatClient:
    if enable_function_calling:
        with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", max_iterations):
            return type("FunctionInvokingMockChatClient", (FunctionInvocationLayer, MockChatClient), {})()
    return MockChatClient()


@fixture
def chat_client_base(enable_function_calling: bool, max_iterations: int) -> MockBaseChatClient:
    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", max_iterations):
        client = MockBaseChatClient()
    if not enable_function_calling:
        client.function_invocation_configuration["enabled"] = False
    return client


# region Agents
class MockAgentThread(AgentThread):
    pass


# Mock Agent implementation for testing
class MockAgent(SupportsAgentRun):
    @property
    def id(self) -> str:
        return str(uuid4())

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        return "Name"

    @property
    def description(self) -> str | None:
        return "Description"

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        thread: AgentThread | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | AsyncIterable[AgentResponseUpdate]:
        if stream:
            return self._run_stream_impl(messages=messages, thread=thread, **kwargs)
        return self._run_impl(messages=messages, thread=thread, **kwargs)

    async def _run_impl(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        logger.debug(f"Running mock agent, with: {messages=}, {thread=}, {kwargs=}")
        return AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text("Response")])])

    async def _run_stream_impl(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        logger.debug(f"Running mock agent stream, with: {messages=}, {thread=}, {kwargs=}")
        yield AgentResponseUpdate(contents=[Content.from_text("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> SupportsAgentRun:
    return MockAgent()
