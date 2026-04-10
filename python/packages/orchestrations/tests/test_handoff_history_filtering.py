# Copyright (c) Microsoft. All rights reserved.

"""Tests for history provider filtering in handoff agent cloning."""

from unittest.mock import MagicMock

from agent_framework import Agent
from agent_framework._sessions import BaseHistoryProvider, InMemoryHistoryProvider
from agent_framework_orchestrations._handoff import HandoffAgentExecutor


class FakeHistoryProvider(BaseHistoryProvider):
    """A concrete history provider for testing the filtering logic."""

    def __init__(self) -> None:
        super().__init__(load_messages=True, store_inputs=True, store_outputs=True)

    async def get_messages(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    async def add_messages(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass


class FakeContextProvider:
    """A non-history context provider that should survive filtering."""

    async def get_context(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []


def _make_agent(context_providers: list | None = None) -> Agent:
    """Create a minimal Agent with mocked client for testing."""
    agent = Agent(
        name="test-agent",
        client=MagicMock(),
        context_providers=context_providers or [],
        require_per_service_call_history_persistence=True,
    )
    return agent


def test_clone_filters_history_providers() -> None:
    """History providers should be filtered out during cloning."""
    history_provider = FakeHistoryProvider()
    other_provider = FakeContextProvider()

    agent = _make_agent(context_providers=[history_provider, other_provider])
    executor = HandoffAgentExecutor.__new__(HandoffAgentExecutor)

    cloned = executor._clone_chat_agent(agent)

    # The FakeHistoryProvider should be filtered out
    provider_types = [type(p) for p in cloned.context_providers]
    assert FakeHistoryProvider not in provider_types

    # The non-history provider should survive
    assert FakeContextProvider in provider_types


def test_clone_adds_noop_history_placeholder() -> None:
    """A no-op InMemoryHistoryProvider should be added to prevent auto-injection."""
    agent = _make_agent(context_providers=[])
    executor = HandoffAgentExecutor.__new__(HandoffAgentExecutor)

    cloned = executor._clone_chat_agent(agent)

    # Should have exactly one InMemoryHistoryProvider (the no-op placeholder)
    history_providers = [
        p for p in cloned.context_providers
        if isinstance(p, InMemoryHistoryProvider)
    ]
    assert len(history_providers) == 1

    # The placeholder should be no-op
    placeholder = history_providers[0]
    assert placeholder.load_messages is False
    assert placeholder.store_inputs is False
    assert placeholder.store_outputs is False


def test_clone_replaces_active_history_with_noop() -> None:
    """An agent with an active history provider should get a no-op replacement after cloning."""
    active_provider = InMemoryHistoryProvider(
        load_messages=True,
        store_inputs=True,
        store_outputs=True,
    )
    agent = _make_agent(context_providers=[active_provider])
    executor = HandoffAgentExecutor.__new__(HandoffAgentExecutor)

    cloned = executor._clone_chat_agent(agent)

    history_providers = [
        p for p in cloned.context_providers
        if isinstance(p, InMemoryHistoryProvider)
    ]
    assert len(history_providers) == 1

    # The original active provider should be replaced with a no-op
    noop = history_providers[0]
    assert noop.load_messages is False
    assert noop.store_inputs is False
    assert noop.store_outputs is False
