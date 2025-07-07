# Copyright (c) Microsoft. All rights reserved.

import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, TypeVar, cast

from pytest import fixture

from agent_framework import Agent, AgentThread, ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole, TextContent

TThreadType = TypeVar("TThreadType", bound=AgentThread)


# Mock AgentThread implementation for testing
class MockAgentThread(AgentThread):
    async def _create(self) -> str:
        return str(uuid.uuid4())

    async def _delete(self) -> None:
        pass

    async def _on_new_message(self, new_message: ChatMessage) -> None:
        pass


# Mock Agent implementation for testing
class MockAgent:
    async def run(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[TextContent("Response")])


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> MockAgent:
    return MockAgent()


async def test_agent_thread_id_property(agent_thread: MockAgentThread) -> None:
    assert agent_thread.id is None
    await agent_thread.create()
    assert isinstance(agent_thread.id, str)


async def test_agent_thread_create(agent_thread: MockAgentThread) -> None:
    thread_id = await agent_thread.create()
    assert thread_id == agent_thread.id
    assert isinstance(thread_id, str)


async def test_agent_thread_create_already_exists(agent_thread: MockAgentThread) -> None:
    thread_id = await agent_thread.create()
    same_id = await agent_thread.create()
    assert thread_id == same_id


async def test_agent_thread_delete_already_deleted(agent_thread: MockAgentThread) -> None:
    await agent_thread.delete()
    await agent_thread.delete()  # Should not raise error


async def test_agent_thread_on_new_message_creates_thread(agent_thread: MockAgentThread) -> None:
    message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
    await agent_thread.on_new_message(message)
    assert agent_thread.id is not None


def test_agent_type(agent: MockAgent) -> None:
    assert isinstance(agent, Agent)


async def test_agent_run(agent: MockAgent) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert cast(TextContent, response.messages[0].contents[0]).text == "Response"


async def tesT_agent_run_stream(agent: MockAgent) -> None:
    async def collect_updates(updates: AsyncIterable[ChatResponseUpdate]) -> list[ChatResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run_stream(messages="test"))
    assert len(updates) == 1
    assert cast(TextContent, updates[0].contents[0]).text == "Response"
