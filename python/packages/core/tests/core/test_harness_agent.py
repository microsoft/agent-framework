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


def test_create_harness_agent_no_token_params_disables_compaction() -> None:
    """When token params are omitted, compaction is automatically disabled."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider not in provider_types


def test_create_harness_agent_no_token_params_skips_max_tokens_option() -> None:
    """When max_output_tokens is omitted, max_tokens should not be set in default options."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
    )
    assert agent.default_options.get("max_tokens") is None


def test_create_harness_agent_custom_before_strategy_enables_compaction_without_tokens() -> None:
    """A custom before_compaction_strategy enables compaction even when token params are omitted."""
    from agent_framework import ToolResultCompactionStrategy

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        before_compaction_strategy=ToolResultCompactionStrategy(),
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider in provider_types


def test_create_harness_agent_disable_compaction_overrides_custom_before_strategy() -> None:
    """disable_compaction=True wins even when a custom before strategy is provided."""
    from agent_framework import ToolResultCompactionStrategy

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        before_compaction_strategy=ToolResultCompactionStrategy(),
        disable_compaction=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider not in provider_types


def test_create_harness_agent_custom_after_strategy_enables_compaction_without_tokens() -> None:
    """A custom after_compaction_strategy enables compaction even when token params are omitted."""
    from agent_framework import ToolResultCompactionStrategy

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        after_compaction_strategy=ToolResultCompactionStrategy(),
    )
    compaction_providers = [p for p in agent.context_providers if isinstance(p, CompactionProvider)]
    assert len(compaction_providers) == 1
    # Before phase is skipped (no token budget, no custom before strategy), after phase is set.
    assert compaction_providers[0].before_strategy is None
    assert compaction_providers[0].after_strategy is not None


# --- Validation Tests ---


def test_create_harness_agent_rejects_invalid_context_tokens() -> None:
    """max_context_window_tokens must be positive."""
    with pytest.raises(ValueError, match="max_context_window_tokens must be positive"):
        create_harness_agent(
            client=_FakeChatClient(),  # type: ignore[arg-type]
            max_context_window_tokens=0,
            max_output_tokens=100,
        )


def test_create_harness_agent_rejects_non_positive_output_tokens() -> None:
    """max_output_tokens must be positive when provided."""
    for invalid_value in (0, -1):
        with pytest.raises(ValueError, match="max_output_tokens must be positive"):
            create_harness_agent(
                client=_FakeChatClient(),  # type: ignore[arg-type]
                max_context_window_tokens=1000,
                max_output_tokens=invalid_value,
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


# --- Background Agents Tests ---


class _FakeBackgroundAgent:
    """Minimal agent stub satisfying SupportsAgentRun for background agents tests."""

    def __init__(self, name: str, description: str | None = None):
        self.id = f"agent-{name}"
        self.name = name
        self.description = description

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    async def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        from agent_framework import AgentResponse

        return AgentResponse(messages=[], response_id="fake-bg-response")


def test_create_harness_agent_no_background_agents_by_default() -> None:
    """No BackgroundAgentsProvider should be included when background_agents is not provided."""
    from agent_framework._harness._background_agents import BackgroundAgentsProvider

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
    )
    providers = agent.context_providers or []
    assert not any(isinstance(p, BackgroundAgentsProvider) for p in providers)


def test_create_harness_agent_adds_background_agents_provider() -> None:
    """BackgroundAgentsProvider should be included when background_agents are provided."""
    from agent_framework._harness._background_agents import BackgroundAgentsProvider

    bg_agent = _FakeBackgroundAgent("WebSearcher", "Searches the web")
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[bg_agent],
    )
    providers = agent.context_providers or []
    bg_providers = [p for p in providers if isinstance(p, BackgroundAgentsProvider)]
    assert len(bg_providers) == 1


def test_create_harness_agent_background_agents_custom_instructions() -> None:
    """Custom instructions should be passed to BackgroundAgentsProvider."""
    from agent_framework._harness._background_agents import BackgroundAgentsProvider

    custom_instructions = "## Custom\n\nUse agents wisely.\n\n{background_agents}"
    bg_agent = _FakeBackgroundAgent("Helper", "A helper agent")
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[bg_agent],
        background_agents_instructions=custom_instructions,
    )
    providers = agent.context_providers or []
    bg_providers = [p for p in providers if isinstance(p, BackgroundAgentsProvider)]
    assert len(bg_providers) == 1
    # Verify the custom instructions were used (placeholder replaced with agent list).
    assert "Custom" in bg_providers[0]._instructions
    assert "Helper" in bg_providers[0]._instructions


def test_create_harness_agent_empty_background_agents_list() -> None:
    """An empty background_agents list should NOT add a BackgroundAgentsProvider."""
    from agent_framework._harness._background_agents import BackgroundAgentsProvider

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[],
    )
    providers = agent.context_providers or []
    assert not any(isinstance(p, BackgroundAgentsProvider) for p in providers)
