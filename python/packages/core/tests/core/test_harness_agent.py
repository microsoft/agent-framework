# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from agent_framework import (
    AgentSession,
    ChatResponse,
    CompactionProvider,
    InMemoryHistoryProvider,
    Message,
    SkillsProvider,
    TodoProvider,
    create_harness_agent,
)
from agent_framework._harness._agent import DEFAULT_HARNESS_INSTRUCTIONS, _assemble_instructions
from agent_framework._harness._mode import AgentModeProvider
from agent_framework._sessions import ContextProvider


class _FakeChatClient:
    """Minimal chat client stub for testing assembly."""

    model = "test-model"

    async def get_response(
        self,
        *,
        messages: list[Message],
        options: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[Message(role="assistant", contents=["Hello"])])

    async def get_streaming_response(
        self,
        *,
        messages: list[Message],
        options: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        yield Message(role="assistant", contents=["Hello"])  # pragma: no cover


# --- Assembly Tests ---


def test_create_harness_agent_with_defaults() -> None:
    """create_harness_agent should assemble successfully with default options."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert agent.id is not None


def test_create_harness_agent_includes_all_default_providers() -> None:
    """Default assembly should include history, compaction, todo, mode (no skills by default)."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    providers = agent.context_providers
    provider_types = [type(p) for p in providers]

    assert InMemoryHistoryProvider in provider_types
    assert CompactionProvider in provider_types
    assert TodoProvider in provider_types
    assert AgentModeProvider in provider_types
    assert SkillsProvider not in provider_types


def test_create_harness_agent_disable_todo() -> None:
    """disable_todo=True should exclude TodoProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_todo=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert TodoProvider not in provider_types


def test_create_harness_agent_disable_mode() -> None:
    """disable_mode=True should exclude AgentModeProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_mode=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert AgentModeProvider not in provider_types


def test_create_harness_agent_disable_memory() -> None:
    """disable_memory=True should exclude MemoryContextProvider even when memory_store is provided."""
    from agent_framework import MemoryContextProvider
    from agent_framework._harness._memory import MemoryStore

    class _FakeMemoryStore(MemoryStore):
        def list_topics(self, session, *, source_id):
            return []

        def get_topic(self, session, *, source_id, topic):
            raise NotImplementedError

        def write_topic(self, session, record, *, source_id):
            pass

        def delete_topic(self, session, *, source_id, topic):
            pass

        def get_index_text(self, session, *, source_id):
            return ""

        def get_transcripts_directory(self, session, *, source_id):
            return ""

        def read_state(self, session, *, source_id):
            return {}

        def rebuild_index(self, session, *, source_id):
            pass

        def search_transcripts(self, session, *, source_id, query):
            return []

        def write_state(self, session, state, *, source_id):
            pass

    # With memory_store provided and disable_memory=False, MemoryContextProvider should be present.
    agent_with_memory = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        memory_store=_FakeMemoryStore(),
    )
    provider_types = [type(p) for p in agent_with_memory.context_providers]
    assert MemoryContextProvider in provider_types

    # With memory_store provided and disable_memory=True, MemoryContextProvider should be absent.
    agent_disabled = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        memory_store=_FakeMemoryStore(),
        disable_memory=True,
    )
    provider_types = [type(p) for p in agent_disabled.context_providers]
    assert MemoryContextProvider not in provider_types


def test_create_harness_agent_skills_paths_adds_provider() -> None:
    """skills_paths should add a SkillsProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        skills_paths=["./test-skills"],
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert SkillsProvider in provider_types


def test_create_harness_agent_disable_compaction() -> None:
    """disable_compaction=True should exclude CompactionProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_compaction=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider not in provider_types


def test_create_harness_agent_returns_full_agent() -> None:
    """Factory should return an Agent instance (with telemetry)."""
    from agent_framework._agents import Agent as FullAgent

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert isinstance(agent, FullAgent)


# --- Validation Tests ---


def test_create_harness_agent_rejects_invalid_context_tokens() -> None:
    """max_context_window_tokens must be positive."""
    with pytest.raises(ValueError, match="max_context_window_tokens must be positive"):
        create_harness_agent(
            client=_FakeChatClient(),  # type: ignore[arg-type]
            max_context_window_tokens=0,
            max_output_tokens=100,
        )


def test_create_harness_agent_rejects_negative_output_tokens() -> None:
    """max_output_tokens must be non-negative."""
    with pytest.raises(ValueError, match="max_output_tokens must be non-negative"):
        create_harness_agent(
            client=_FakeChatClient(),  # type: ignore[arg-type]
            max_context_window_tokens=1000,
            max_output_tokens=-1,
        )


def test_create_harness_agent_rejects_output_gte_context() -> None:
    """max_output_tokens must be less than max_context_window_tokens."""
    with pytest.raises(ValueError, match="max_output_tokens must be less than"):
        create_harness_agent(
            client=_FakeChatClient(),  # type: ignore[arg-type]
            max_context_window_tokens=1000,
            max_output_tokens=1000,
        )


# --- Instructions Tests ---


def test_default_instructions() -> None:
    """None args should produce default harness instructions."""
    result = _assemble_instructions(None, None)
    assert result == DEFAULT_HARNESS_INSTRUCTIONS.strip()


def test_custom_agent_instructions_appended() -> None:
    """Agent instructions should be appended after harness instructions."""
    result = _assemble_instructions(None, "Focus on code review.")
    assert DEFAULT_HARNESS_INSTRUCTIONS in result  # type: ignore[operator]
    assert "Focus on code review." in result  # type: ignore[operator]


def test_empty_harness_instructions_uses_agent_only() -> None:
    """Empty harness_instructions should return agent instructions only."""
    result = _assemble_instructions("", "Custom only.")
    assert result == "Custom only."


# --- Identity Tests ---


def test_create_harness_agent_custom_identity() -> None:
    """Custom id, name, description should propagate."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        id="my-agent-id",
        name="my-agent",
        description="A test agent",
    )
    assert agent.id == "my-agent-id"
    assert agent.name == "my-agent"
    assert agent.description == "A test agent"


# --- Session Tests ---


def test_create_harness_agent_create_session() -> None:
    """create_session should return an AgentSession."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    session = agent.create_session()
    assert isinstance(session, AgentSession)


def test_create_harness_agent_create_session_with_id() -> None:
    """create_session should accept a custom session_id."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    session = agent.create_session(session_id="custom-id")
    assert session.session_id == "custom-id"


async def test_create_harness_agent_run_returns_response() -> None:
    """agent.run() should return a response."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    session = agent.create_session()
    response = await agent.run("hello", session=session)
    assert response.messages
    assert response.messages[-1].role == "assistant"


# --- Protocol Tests ---


def test_create_harness_agent_satisfies_protocol() -> None:
    """Returned agent should satisfy SupportsAgentRun protocol."""
    from agent_framework import SupportsAgentRun

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert isinstance(agent, SupportsAgentRun)


# --- Additional providers ---


def test_create_harness_agent_extra_context_providers() -> None:
    """Additional context_providers should be appended."""

    class _CustomProvider(ContextProvider):
        pass

    custom = _CustomProvider("custom")
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        context_providers=[custom],
    )
    assert custom in agent.context_providers


# --- Web Search Tool Tests ---


class _FakeWebSearchClient(_FakeChatClient):
    """Fake client that supports web search tool."""

    def get_web_search_tool(self, **kwargs: Any) -> str:
        return "web_search_tool_instance"


def test_create_harness_agent_auto_adds_web_search_tool() -> None:
    """Web search tool should be auto-added when client supports it."""
    agent = create_harness_agent(
        client=_FakeWebSearchClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    tools = agent.default_options.get("tools", [])
    assert "web_search_tool_instance" in tools


def test_create_harness_agent_disable_web_search() -> None:
    """disable_web_search=True should skip auto-adding the web search tool."""
    agent = create_harness_agent(
        client=_FakeWebSearchClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
    )
    tools = agent.default_options.get("tools", [])
    assert "web_search_tool_instance" not in tools


def test_create_harness_agent_no_web_search_when_unsupported() -> None:
    """Web search tool should NOT be added when client does not support it."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    tools = agent.default_options.get("tools", [])
    assert "web_search_tool_instance" not in tools


def test_create_harness_agent_logs_warning_when_no_web_search(caplog: pytest.LogCaptureFixture) -> None:
    """A warning should be logged when client doesn't support web search."""
    import logging

    with caplog.at_level(logging.WARNING, logger="agent_framework._harness._agent"):
        create_harness_agent(
            client=_FakeChatClient(),  # type: ignore[arg-type]
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
        )
    assert any("SupportsWebSearchTool" in msg for msg in caplog.messages)
