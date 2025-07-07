# Copyright (c) Microsoft. All rights reserved.

import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, TypeVar
from unittest.mock import AsyncMock

import pytest

from agent_framework import Agent, AgentThread, ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole, TextContent
from agent_framework.exceptions import AgentExecutionException

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
class MockAgent(Agent):
    async def get_response(  # type: ignore
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        return AsyncMock(
            return_value=ChatResponse(
                messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])]
            )
        )

    async def invoke(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponse]:
        yield ChatResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def invoke_stream(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[TextContent("Response")])


@pytest.fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@pytest.fixture
def agent() -> Agent:
    return MockAgent()


@pytest.mark.asyncio
async def test_agent_thread_id_property(agent_thread: MockAgentThread) -> None:
    assert agent_thread.id is None
    await agent_thread.create()
    assert isinstance(agent_thread.id, str)


@pytest.mark.asyncio
async def test_agent_thread_create(agent_thread: MockAgentThread) -> None:
    thread_id = await agent_thread.create()
    assert thread_id == agent_thread.id
    assert isinstance(thread_id, str)


@pytest.mark.asyncio
async def test_agent_thread_create_already_exists(agent_thread: MockAgentThread) -> None:
    thread_id = await agent_thread.create()
    same_id = await agent_thread.create()
    assert thread_id == same_id


@pytest.mark.asyncio
async def test_agent_thread_delete_already_deleted(agent_thread: MockAgentThread) -> None:
    await agent_thread.delete()
    await agent_thread.delete()  # Should not raise error


@pytest.mark.asyncio
async def test_agent_thread_on_new_message_creates_thread(agent_thread: MockAgentThread) -> None:
    message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
    await agent_thread.on_new_message(message)
    assert agent_thread.id is not None


@pytest.mark.asyncio
async def test_agent_thread_create_after_delete_raises(agent_thread: MockAgentThread) -> None:
    await agent_thread.delete()
    with pytest.raises(RuntimeError, match="Thread has already been deleted"):
        await agent_thread.create()


@pytest.mark.asyncio
async def test_agent_thread_id_after_delete_raises(agent_thread: MockAgentThread) -> None:
    await agent_thread.delete()
    with pytest.raises(RuntimeError, match="Thread has been deleted"):
        _ = agent_thread.id


@pytest.mark.asyncio
async def test_agent_ensure_thread_exists_with_messages(agent: MockAgent) -> None:
    message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
    thread = await agent._ensure_thread_exists_with_messages(  # type: ignore
        messages=[message], thread=None, construct_thread=MockAgentThread, expected_type=MockAgentThread
    )
    assert isinstance(thread, MockAgentThread)
    assert thread.id is not None


@pytest.mark.asyncio
async def test_agent_ensure_thread_exists_wrong_type(agent: MockAgent) -> None:
    class WrongThread(AgentThread):
        async def _create(self) -> str:
            return str(uuid.uuid4())

        async def _delete(self) -> None:
            pass

        async def _on_new_message(self, new_message: ChatMessage) -> None:
            pass

    with pytest.raises(AgentExecutionException, match="only supports agent threads of type MockAgentThread"):
        await agent._ensure_thread_exists_with_messages(  # type: ignore
            messages=None, thread=WrongThread(), construct_thread=MockAgentThread, expected_type=MockAgentThread
        )


@pytest.mark.asyncio
async def test_agent_notify_thread_of_new_message(agent: MockAgent, agent_thread: MockAgentThread) -> None:
    message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
    await agent._notify_thread_of_new_message(agent_thread, message)  # type: ignore
    assert agent_thread.id is not None


def test_agent_equality() -> None:
    agent1 = MockAgent(id="123", name="Agent1", description="Desc", instructions="Instruct")
    agent2 = MockAgent(id="123", name="Agent1", description="Desc", instructions="Instruct")
    agent3 = MockAgent(id="456", name="Agent2", description="Desc", instructions="Instruct")
    assert agent1 == agent2
    assert agent1 != agent3
    assert agent1 != "not an agent"


def test_agent_hash() -> None:
    agent1 = MockAgent(id="123", name="Agent1", description="Desc", instructions="Instruct")
    agent2 = MockAgent(id="123", name="Agent1", description="Desc", instructions="Instruct")
    assert hash(agent1) == hash(agent2)
