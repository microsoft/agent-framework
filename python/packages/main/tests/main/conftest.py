# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
from collections.abc import AsyncIterable, MutableSequence
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from pydantic import BaseModel, Field
from pytest import fixture

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
    ToolProtocol,
    ai_function,
    use_function_invocation,
)

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore
else:
    from typing_extensions import override  # type: ignore[import]
# region Chat History

logger = logging.getLogger(__name__)


@fixture(scope="function")
def chat_history() -> list[ChatMessage]:
    return []


# region Tools


@fixture
def ai_tool() -> ToolProtocol:
    """Returns a generic ToolProtocol."""

    class GenericTool(BaseModel):
        name: str
        description: str
        additional_properties: dict[str, Any] | None = None

        def parameters(self) -> dict[str, Any]:
            """Return the parameters of the tool as a JSON schema."""
            return {
                "name": {"type": "string"},
            }

    return GenericTool(name="generic_tool", description="A generic tool")


@fixture
def ai_function_tool() -> ToolProtocol:
    """Returns a executable ToolProtocol."""

    @ai_function
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function


# region Chat Clients
class MockChatClient:
    """Simple implementation of a chat client."""

    def __init__(self) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.call_count: int = 0
        self.responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        logger.debug(f"Running custom chat client, with: {messages=}, {kwargs=}")
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return ChatResponse(messages=ChatMessage(role="assistant", text="test response"))

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        logger.debug(f"Running custom chat client stream, with: {messages=}, {kwargs=}")
        self.call_count += 1
        if self.streaming_responses:
            for update in self.streaming_responses.pop(0):
                yield update
        else:
            yield ChatResponseUpdate(text=TextContent(text="test streaming response "), role="assistant")
            yield ChatResponseUpdate(contents=[TextContent(text="another update")], role="assistant")


class MockBaseChatClient(BaseChatClient):
    """Mock implementation of the BaseChatClient."""

    run_responses: list[ChatResponse] = Field(default_factory=list)
    streaming_responses: list[list[ChatResponseUpdate]] = Field(default_factory=list)

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request to the AI service.

        Args:
            messages: The chat messages to send.
            chat_options: The options for the request.
            kwargs: Any additional keyword arguments.

        Returns:
            The chat response contents representing the response(s).
        """
        logger.debug(f"Running base chat client inner, with: {messages=}, {chat_options=}, {kwargs=}")
        if not self.run_responses:
            return ChatResponse(messages=ChatMessage(role="assistant", text=f"test response - {messages[0].text}"))

        response = self.run_responses.pop(0)

        if chat_options.tool_choice == "none":
            return ChatResponse(
                messages=ChatMessage(
                    role="assistant",
                    text="I broke out of the function invocation loop...",
                ),
                conversation_id=response.conversation_id,
            )

        return response

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        logger.debug(f"Running base chat client inner stream, with: {messages=}, {chat_options=}, {kwargs=}")
        if not self.streaming_responses:
            yield ChatResponseUpdate(text=f"update - {messages[0].text}", role="assistant")
            return
        if chat_options.tool_choice == "none":
            yield ChatResponseUpdate(text="I broke out of the function invocation loop...", role="assistant")
            return
        response = self.streaming_responses.pop(0)
        for update in response:
            yield update
        await asyncio.sleep(0)


@fixture
def enable_function_calling(request: Any) -> bool:
    return request.param if hasattr(request, "param") else True


@fixture
def max_iterations(request: Any) -> int:
    return request.param if hasattr(request, "param") else 2


@fixture
def chat_client(enable_function_calling: bool, max_iterations: int) -> MockChatClient:
    if enable_function_calling:
        with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", max_iterations):
            return use_function_invocation(MockChatClient)()
    return MockChatClient()


@fixture
def chat_client_base(enable_function_calling: bool, max_iterations: int) -> MockBaseChatClient:
    if enable_function_calling:
        with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", max_iterations):
            return use_function_invocation(MockBaseChatClient)()
    return MockBaseChatClient()


# region Agents
class MockAgentThread(AgentThread):
    pass


# Mock Agent implementation for testing
class MockAgent(AgentProtocol):
    @property
    def id(self) -> str:
        return str(uuid4())

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        return "Name"

    @property
    def display_name(self) -> str:
        """Returns the name of the agent."""
        return "Display Name"

    @property
    def description(self) -> str | None:
        return "Description"

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        logger.debug(f"Running mock agent, with: {messages=}, {thread=}, {kwargs=}")
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        logger.debug(f"Running mock agent stream, with: {messages=}, {thread=}, {kwargs=}")
        yield AgentRunResponseUpdate(contents=[TextContent("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> AgentProtocol:
    return MockAgent()
