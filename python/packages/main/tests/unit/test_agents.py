# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Sequence
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field
from pytest import fixture

from agent_framework import (
    Agent,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatMessage,
    ChatRole,
    TextContent,
)

TThreadType = TypeVar("TThreadType", bound=AgentThread)


# Mock AgentThread implementation for testing
class MockAgentThread(AgentThread):
    async def _create(self) -> str:
        return str(uuid4())

    async def _delete(self) -> None:
        pass

    async def _on_new_message(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        pass


# Mock Agent implementation for testing
class MockAgent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str | None = None
    description: str | None = None

    async def run(
        self,
        messages: ChatMessage | str | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[TextContent("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> Agent:
    return MockAgent()


def test_agent_thread_type(agent_thread: AgentThread) -> None:
    assert isinstance(agent_thread, AgentThread)


async def test_agent_thread_id_property(agent_thread: AgentThread) -> None:
    assert agent_thread.id is None
    await agent_thread.create()
    assert isinstance(agent_thread.id, str)


async def test_agent_thread_create(agent_thread: AgentThread) -> None:
    thread_id = await agent_thread.create()
    assert thread_id == agent_thread.id
    assert isinstance(thread_id, str)


async def test_agent_thread_create_already_exists(agent_thread: AgentThread) -> None:
    thread_id = await agent_thread.create()
    same_id = await agent_thread.create()
    assert thread_id == same_id


async def test_agent_thread_delete_already_deleted(agent_thread: AgentThread) -> None:
    await agent_thread.delete()
    await agent_thread.delete()  # Should not raise error


async def test_agent_thread_on_new_message_creates_thread(agent_thread: AgentThread) -> None:
    message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])
    await agent_thread.on_new_message(message)
    assert agent_thread.id is not None


def test_agent_type(agent: Agent) -> None:
    assert isinstance(agent, Agent)


async def test_agent_run(agent: Agent) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert response.messages[0].text == "Response"


async def test_agent_run_stream(agent: Agent) -> None:
    async def collect_updates(updates: AsyncIterable[AgentRunResponseUpdate]) -> list[AgentRunResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run_stream(messages="test"))
    assert len(updates) == 1
    assert updates[0].text == "Response"
