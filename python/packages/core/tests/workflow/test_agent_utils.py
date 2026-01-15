# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any

from agent_framework import AgentResponse, AgentResponseUpdate, AgentThread, ChatMessage
from agent_framework._workflows._agent_utils import resolve_agent_id


class MockAgent:
    """Mock agent for testing agent utilities."""

    def __init__(self, agent_id: str, name: str | None = None) -> None:
        self._id = agent_id
        self._name = name

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent."""
        ...

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        ...

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse: ...

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]: ...

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        ...


def test_resolve_agent_id_with_name() -> None:
    """Test that resolve_agent_id returns name when agent has a name."""
    agent = MockAgent(agent_id="agent-123", name="MyAgent")
    result = resolve_agent_id(agent)
    assert result == "MyAgent"


def test_resolve_agent_id_without_name() -> None:
    """Test that resolve_agent_id returns id when agent has no name."""
    agent = MockAgent(agent_id="agent-456", name=None)
    result = resolve_agent_id(agent)
    assert result == "agent-456"


def test_resolve_agent_id_with_empty_name() -> None:
    """Test that resolve_agent_id returns id when agent has empty string name."""
    agent = MockAgent(agent_id="agent-789", name="")
    result = resolve_agent_id(agent)
    assert result == "agent-789"


def test_resolve_agent_id_prefers_name_over_id() -> None:
    """Test that resolve_agent_id prefers name over id when both are set."""
    agent = MockAgent(agent_id="agent-abc", name="PreferredName")
    result = resolve_agent_id(agent)
    assert result == "PreferredName"
    assert result != "agent-abc"
