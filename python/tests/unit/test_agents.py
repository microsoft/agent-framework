# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Sequence
from typing import Any
from uuid import uuid4

from pytest import fixture

from agent_framework import Agent, AgentThread, ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole, TextContent


# Mock AgentThread implementation for testing
class MockAgentThread(AgentThread):
    async def _on_new_messages(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        pass


# Mock Agent implementation for testing
class MockAgent(Agent):
    @property
    def id(self) -> str:
        return str(uuid4())

    @property
    def name(self) -> str | None:
        return None

    @property
    def description(self) -> str | None:
        return None

    @property
    def instructions(self) -> str | None:
        return None

    async def run(
        self,
        messages: ChatMessage | str | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[TextContent("Response")])

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


def test_agent_type(agent: Agent) -> None:
    assert isinstance(agent, Agent)


async def test_agent_run(agent: Agent) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert response.messages[0].text == "Response"


async def test_agent_run_stream(agent: Agent) -> None:
    async def collect_updates(updates: AsyncIterable[ChatResponseUpdate]) -> list[ChatResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run_stream(messages="test"))
    assert len(updates) == 1
    assert updates[0].text == "Response"
