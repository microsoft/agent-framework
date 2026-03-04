# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable
from typing import Any, Literal, overload

from agent_framework import AgentResponse, AgentResponseUpdate, AgentRunInputs, AgentSession, ResponseStream
from agent_framework._workflows._agent_utils import resolve_agent_id


class MockAgent:
    """Mock agent for testing agent utilities."""

    def __init__(self, agent_id: str, name: str | None = None) -> None:
        self.id: str = agent_id
        self.name: str | None = name
        self.description: str | None = None

    @overload
    def run(self, messages: AgentRunInputs | None = ..., *, stream: Literal[False] = ..., session: AgentSession | None = ..., **kwargs: Any) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(self, messages: AgentRunInputs | None = ..., *, stream: Literal[True], session: AgentSession | None = ..., **kwargs: Any) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...
    def run(self, messages: AgentRunInputs | None = None, *, stream: bool = False, session: AgentSession | None = None, **kwargs: Any) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def create_session(self, **kwargs: Any) -> AgentSession:
        """Creates a new conversation session for the agent."""
        ...

    def get_session(self, *, service_session_id: str, **kwargs: Any) -> AgentSession:
        return AgentSession()


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
