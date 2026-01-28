# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
from collections.abc import AsyncIterable, MutableSequence
from typing import Any, Generic
from unittest.mock import patch
from uuid import uuid4

from pydantic import BaseModel
from pytest import fixture

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Role,
    ToolProtocol,
    tool,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._clients import TOptions_co

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
def tool_tool() -> ToolProtocol:
    """Returns a executable ToolProtocol."""

    @tool(approval_mode="never_require")
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
            yield ChatResponseUpdate(text=Content.from_text(text="test streaming response "), role="assistant")
            yield ChatResponseUpdate(contents=[Content.from_text(text="another update")], role="assistant")


@use_chat_middleware
class MockBaseChatClient(BaseChatClient[TOptions_co], Generic[TOptions_co]):
    """Mock implementation of the BaseChatClient."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.run_responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []
        self.call_count: int = 0

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request to the AI service.

        Args:
            messages: The chat messages to send.
            options: The options dict for the request.
            kwargs: Any additional keyword arguments.

        Returns:
            The chat response contents representing the response(s).
        """
        logger.debug(f"Running base chat client inner, with: {messages=}, {options=}, {kwargs=}")
        self.call_count += 1
        if not self.run_responses:
            return ChatResponse(messages=ChatMessage(role="assistant", text=f"test response - {messages[-1].text}"))

        response = self.run_responses.pop(0)

        if options.get("tool_choice") == "none":
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
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        logger.debug(f"Running base chat client inner stream, with: {messages=}, {options=}, {kwargs=}")
        if not self.streaming_responses:
            yield ChatResponseUpdate(text=f"update - {messages[0].text}", role="assistant")
            return
        if options.get("tool_choice") == "none":
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
    def description(self) -> str | None:
        return "Description"

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        logger.debug(f"Running mock agent, with: {messages=}, {thread=}, {kwargs=}")
        return AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
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
def agent() -> AgentProtocol:
    return MockAgent()
