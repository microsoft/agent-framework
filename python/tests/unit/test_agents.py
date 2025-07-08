# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, List, TypeVar, cast

from pytest import fixture, raises

from agent_framework import (
    Agent,
    AgentThread,
    ChatClientAgentThread,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    TextContent,
)

TThreadType = TypeVar("TThreadType", bound=AgentThread)


# region MockAgentThread


class MockAgentThread(AgentThread):
    def __init__(self) -> None:
        self.chat_messages: List[ChatMessage] = []

    async def _on_new_message(self, new_message: ChatMessage) -> None:
        self.chat_messages.append(new_message)


# region MockAgent


class MockAgent(Agent):
    async def run(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[TextContent("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


# region AgentThread tests


class TestAgentThread:
    @fixture
    def agent_thread(self) -> AgentThread:
        return MockAgentThread()

    async def test_agent_thread_on_new_message_creates_thread(self, agent_thread: MockAgentThread) -> None:
        message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
        await agent_thread.on_new_message(message)
        assert cast(TextContent, agent_thread.chat_messages[0].contents[0]).text == "Hello"


# region Agent tests


class TestAgent:
    @fixture
    def agent(self) -> MockAgent:
        return MockAgent()

    def test_agent_type(self, agent: MockAgent) -> None:
        assert isinstance(agent, Agent)

    async def test_agent_run(self, agent: MockAgent) -> None:
        response = await agent.run("test")
        assert response.messages[0].role == ChatRole.ASSISTANT
        assert cast(TextContent, response.messages[0].contents[0]).text == "Response"

    async def test_agent_run_stream(self, agent: MockAgent) -> None:
        async def collect_updates(updates: AsyncIterable[ChatResponseUpdate]) -> list[ChatResponseUpdate]:
            return [u async for u in updates]

        updates = await collect_updates(agent.run_stream(messages="test"))
        assert len(updates) == 1
        assert cast(TextContent, updates[0].contents[0]).text == "Response"

    def test_agent_get_new_thread(self, agent: MockAgent) -> None:
        thread = agent.get_new_thread()
        assert isinstance(thread, MockAgentThread)


# region ChatClientAgentThread tests


class TestChatClientAgentThread:
    def test_init_with_both_id_and_messages_raises_value_error(self) -> None:
        with raises(ValueError, match="Cannot specify both id and messages"):
            ChatClientAgentThread(
                id="test_id", messages=[ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])]
            )

    def test_init_with_empty_id_raises_value_error(self) -> None:
        with raises(ValueError, match="ID cannot be empty or whitespace"):
            ChatClientAgentThread(id="   ")

    async def test_init_with_valid_id(self) -> None:
        thread = ChatClientAgentThread(id="test_id")
        messages = [msg async for msg in thread.get_messages()]

        assert thread.id == "test_id"
        assert len(messages) == 0

    async def test_init_with_messages(self) -> None:
        messages = [ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])]
        thread = ChatClientAgentThread(messages=messages)
        thread_messages = [msg async for msg in thread.get_messages()]
        assert thread.id is None
        assert thread_messages == messages

    async def test_get_messages_empty(self) -> None:
        thread = ChatClientAgentThread()
        messages = [msg async for msg in thread.get_messages()]
        assert messages == []

    async def test_on_new_message_local_thread(self) -> None:
        thread = ChatClientAgentThread()
        new_message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
        await cast(AgentThread, thread).on_new_message(new_message)
        messages = [msg async for msg in thread.get_messages()]
        assert messages == [new_message]

    async def test_on_new_message_server_thread(self) -> None:
        thread = ChatClientAgentThread(id="test_id")
        new_message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
        await cast(AgentThread, thread).on_new_message(new_message)
        messages = [msg async for msg in thread.get_messages()]
        assert messages == []
