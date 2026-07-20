# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from agent_framework_tools.shell import ShellResult

from agent_framework import (
    AgentSession,
    BaseChatClient,
    CharacterEstimatorTokenizer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CompactionProvider,
    Content,
    ContextWindowCompactionStrategy,
    FileAccessProvider,
    FileMemoryProvider,
    FileSystemAgentFileStore,
    InMemoryAgentFileStore,
    InMemoryHistoryProvider,
    Message,
    MessageInjectionMiddleware,
    ResponseStream,
    ServiceSessionId,
    SkillsProvider,
    TodoProvider,
    create_harness_agent,
)
from agent_framework._harness._agent import DEFAULT_HARNESS_INSTRUCTIONS, _assemble_instructions
from agent_framework._harness._mode import AgentModeProvider
from agent_framework._sessions import ContextProvider, PerServiceCallHistoryPersistingMiddleware
from agent_framework._tools import FunctionInvocationLayer


class _FakeChatClient(BaseChatClient[ChatOptions[Any]]):
    """Minimal chat client stub for testing assembly."""

    model = "test-model"

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._get_streaming_response()

        async def _get() -> ChatResponse:
            return ChatResponse(messages=[Message(role="assistant", contents=["Hello"])])

        return _get()

    def _get_streaming_response(self) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            yield ChatResponseUpdate(contents=[Content.from_text("Hello")], role="assistant")  # pragma: no cover

        return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)


# --- Assembly Tests ---


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test in a temp directory so default file stores don't write into the repo."""
    monkeypatch.chdir(tmp_path)


def test_create_harness_agent_with_defaults() -> None:
    """create_harness_agent should assemble successfully with default options."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert agent.id is not None


def test_create_harness_agent_includes_all_default_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default assembly should include history, compaction, todo, mode, and file memory."""
    monkeypatch.chdir(tmp_path)
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    providers = agent.context_providers
    provider_types = [type(p) for p in providers]

    assert InMemoryHistoryProvider in provider_types
    assert CompactionProvider in provider_types
    assert TodoProvider in provider_types
    assert AgentModeProvider in provider_types
    assert FileMemoryProvider in provider_types
    assert SkillsProvider not in provider_types


def test_create_harness_agent_disable_todo() -> None:
    """disable_todo=True should exclude TodoProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_todo=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert TodoProvider not in provider_types


def test_create_harness_agent_disable_mode() -> None:
    """disable_mode=True should exclude AgentModeProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_mode=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert AgentModeProvider not in provider_types


def test_create_harness_agent_disable_file_memory() -> None:
    """disable_file_memory=True should exclude the FileMemoryProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_file_memory=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert FileMemoryProvider not in provider_types


def test_create_harness_agent_file_access_is_opt_in() -> None:
    """FileAccessProvider is absent by default and added only when file_access_store is set."""
    default_agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert FileAccessProvider not in [type(p) for p in default_agent.context_providers]
    # The file memory provider should remain active by default.
    assert FileMemoryProvider in [type(p) for p in default_agent.context_providers]

    access_store = InMemoryAgentFileStore()
    opt_in_agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        file_access_store=access_store,
    )
    access_provider = next(p for p in opt_in_agent.context_providers if isinstance(p, FileAccessProvider))
    assert access_provider.store is access_store


def test_create_harness_agent_uses_custom_file_stores() -> None:
    """Custom file stores should be used by the file memory and file access providers."""
    memory_store = InMemoryAgentFileStore()
    access_store = InMemoryAgentFileStore()
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        file_memory_store=memory_store,
        file_access_store=access_store,
    )

    memory_provider = next(p for p in agent.context_providers if isinstance(p, FileMemoryProvider))
    access_provider = next(p for p in agent.context_providers if isinstance(p, FileAccessProvider))
    assert memory_provider.store is memory_store
    assert access_provider.store is access_store


def test_create_harness_agent_file_access_approval_opt_outs() -> None:
    """The file_access_ approval flags should reach the FileAccessProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        file_access_store=InMemoryAgentFileStore(),
        file_access_disable_readonly_tool_approval=True,
        file_access_disable_write_tool_approval=True,
    )

    access_provider = next(p for p in agent.context_providers if isinstance(p, FileAccessProvider))
    assert access_provider.disable_readonly_tool_approval is True
    assert access_provider.disable_write_tool_approval is True


def test_create_harness_agent_default_file_stores_are_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a custom store, the FileMemoryProvider defaults to FileSystemAgentFileStore in cwd."""
    monkeypatch.chdir(tmp_path)
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )

    memory_provider = next(p for p in agent.context_providers if isinstance(p, FileMemoryProvider))
    assert isinstance(memory_provider.store, FileSystemAgentFileStore)
    assert memory_provider.store.root_path == (tmp_path / "agent-file-memory").resolve()


def test_create_harness_agent_skills_paths_adds_provider() -> None:
    """skills_paths should add a SkillsProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        skills_paths=["./test-skills"],
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert SkillsProvider in provider_types


def test_create_harness_agent_skills_paths_single_str() -> None:
    """skills_paths should accept a single str (not wrapped in a list)."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        skills_paths="./test-skills",
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert SkillsProvider in provider_types


def test_create_harness_agent_skills_paths_single_path(tmp_path: Path) -> None:
    """skills_paths should accept a single pathlib.Path (not wrapped in a list)."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        skills_paths=tmp_path,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert SkillsProvider in provider_types


def test_create_harness_agent_skills_paths_sequence_of_paths(tmp_path: Path) -> None:
    """skills_paths should accept a sequence of pathlib.Path objects."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        skills_paths=[tmp_path, tmp_path / "sub"],
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert SkillsProvider in provider_types


def test_create_harness_agent_disable_compaction() -> None:
    """disable_compaction=True should exclude CompactionProvider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
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
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert isinstance(agent, FullAgent)


def test_create_harness_agent_no_token_params_disables_compaction() -> None:
    """When token params are omitted, compaction is automatically disabled."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider not in provider_types


def test_create_harness_agent_no_token_params_skips_max_tokens_option() -> None:
    """When max_output_tokens is omitted, max_tokens should not be set in default options."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
    )
    assert agent.default_options.get("max_tokens") is None


def test_create_harness_agent_custom_before_strategy_wires_compaction_strategy_without_tokens() -> None:
    """A custom before_compaction_strategy is wired as the agent compaction_strategy, even without tokens."""
    from agent_framework import ToolResultCompactionStrategy

    before_strategy = ToolResultCompactionStrategy()
    agent = create_harness_agent(
        client=_FakeChatClient(),
        before_compaction_strategy=before_strategy,
    )
    # The before-strategy runs per model call via the agent compaction_strategy option, not a provider.
    assert agent.compaction_strategy is before_strategy
    # No after-strategy and no token budget, so no CompactionProvider is added.
    assert CompactionProvider not in [type(p) for p in agent.context_providers]


def test_create_harness_agent_disable_compaction_overrides_custom_before_strategy() -> None:
    """disable_compaction=True wins even when a custom before strategy is provided."""
    from agent_framework import ToolResultCompactionStrategy

    agent = create_harness_agent(
        client=_FakeChatClient(),
        before_compaction_strategy=ToolResultCompactionStrategy(),
        disable_compaction=True,
    )
    provider_types = [type(p) for p in agent.context_providers]
    assert CompactionProvider not in provider_types
    assert agent.compaction_strategy is None


def test_create_harness_agent_custom_after_strategy_enables_compaction_without_tokens() -> None:
    """A custom after_compaction_strategy enables compaction even when token params are omitted."""
    from agent_framework import ToolResultCompactionStrategy

    agent = create_harness_agent(
        client=_FakeChatClient(),
        after_compaction_strategy=ToolResultCompactionStrategy(),
    )
    compaction_providers = [p for p in agent.context_providers if isinstance(p, CompactionProvider)]
    assert len(compaction_providers) == 1
    # Before phase is skipped (no token budget, no custom before strategy), after phase is set.
    assert compaction_providers[0].before_strategy is None
    assert compaction_providers[0].after_strategy is not None
    # An after-only strategy must not wire anything as the agent-level (per-call) compaction.
    assert agent.compaction_strategy is None


def test_create_harness_agent_default_tokens_split_compaction_phases() -> None:
    """With token params, the before-strategy is the agent compaction_strategy; after stays on the provider."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    # Before-strategy runs per model call via the agent option (issue #7011).
    assert isinstance(agent.compaction_strategy, ContextWindowCompactionStrategy)
    # After-strategy runs post-turn via the provider, which no longer carries a before-strategy.
    compaction_providers = [p for p in agent.context_providers if isinstance(p, CompactionProvider)]
    assert len(compaction_providers) == 1
    assert compaction_providers[0].before_strategy is None
    # Both phases default to the same shared ContextWindowCompactionStrategy instance.
    assert isinstance(compaction_providers[0].after_strategy, ContextWindowCompactionStrategy)
    assert compaction_providers[0].after_strategy is agent.compaction_strategy


async def test_before_strategy_compaction_fires_on_loaded_history_under_per_service_call_persistence(
    chat_client_base: Any,
) -> None:
    """Regression for #7011: before-strategy compaction runs per model call on the loaded history.

    Because the harness enables per-service-call persistence, wiring the before-strategy as a
    ``CompactionProvider.before_run`` hook was a no-op (empty context). Wiring it as the agent
    ``compaction_strategy`` option makes it run inside ``BaseChatClient.get_response`` on the full
    history that ``PerServiceCallHistoryPersistingMiddleware`` loads into the outgoing messages.
    """
    captured: dict[str, list[Message]] = {}

    async def fake_get_response(*, messages: Sequence[Message], options: dict[str, Any], **kwargs: Any) -> ChatResponse:
        captured["messages"] = list(messages)
        return ChatResponse(messages=Message(role="assistant", contents=["ok"]))

    def build_agent(*, disable_compaction: bool) -> Any:
        return create_harness_agent(
            client=chat_client_base,
            max_context_window_tokens=2_000,
            max_output_tokens=500,
            tokenizer=CharacterEstimatorTokenizer(),
            disable_compaction=disable_compaction,
            disable_todo=True,
            disable_mode=True,
            disable_file_memory=True,
        )

    def seeded_session(agent: Any) -> tuple[Any, int]:
        session = agent.create_session()
        long_history: list[Message] = []
        for i in range(20):
            long_history.append(Message(role="user", contents=[f"u{i} " * 50]))
            long_history.append(Message(role="assistant", contents=[f"a{i} " * 50]))
        session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID] = {"messages": long_history}
        return session, len(long_history)

    with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
        # Control: compaction disabled -> the full loaded history reaches the leaf client.
        control_agent = build_agent(disable_compaction=True)
        control_session, history_len = seeded_session(control_agent)
        assert control_agent.compaction_strategy is None
        await control_agent.run("final question", session=control_session)
        baseline_count = len(captured["messages"])
        assert baseline_count == history_len + 1  # loaded history + the input message

        # Compaction enabled -> the before-strategy truncates the loaded history per model call.
        compacting_agent = build_agent(disable_compaction=False)
        compacting_session, _ = seeded_session(compacting_agent)
        assert isinstance(compacting_agent.compaction_strategy, ContextWindowCompactionStrategy)
        await compacting_agent.run("final question", session=compacting_session)
        compacted_count = len(captured["messages"])

    # Truncation dropped older messages from the model input, proving the before-strategy fired
    # on the history loaded by per-service-call persistence.
    assert compacted_count < baseline_count


async def test_before_strategy_compaction_multi_turn_keeps_persisted_history_coherent(
    chat_client_base: Any,
) -> None:
    """The per-call before-strategy must not corrupt or lose persisted history across turns.

    The before-strategy runs on a per-call shallow copy that shares ``Message`` objects with the
    stored history, so its ``_excluded`` annotations leak onto those shared objects. With the
    default ``skip_excluded=False`` the provider reloads every message each turn, so stored history
    must keep growing by exactly the persisted input/output of each turn (no loss, no duplication,
    no leaked per-call summaries).
    """
    per_call_counts: list[int] = []

    async def fake_get_response(*, messages: Sequence[Message], options: dict[str, Any], **kwargs: Any) -> ChatResponse:
        per_call_counts.append(len(messages))
        return ChatResponse(messages=Message(role="assistant", contents=["ok"]))

    agent = create_harness_agent(
        client=chat_client_base,
        max_context_window_tokens=2_000,
        max_output_tokens=500,
        tokenizer=CharacterEstimatorTokenizer(),
        disable_todo=True,
        disable_mode=True,
        disable_file_memory=True,
    )

    session = agent.create_session()
    long_history: list[Message] = []
    for i in range(15):
        long_history.append(Message(role="user", contents=[f"u{i} " * 50]))
        long_history.append(Message(role="assistant", contents=[f"a{i} " * 50]))
    history_len = len(long_history)
    session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID] = {"messages": long_history}

    with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=fake_get_response):
        await agent.run("first question", session=session)
        await agent.run("second question", session=session)

    # Compaction fired on both turns: each model call saw far fewer messages than were persisted.
    assert len(per_call_counts) == 2
    assert all(0 < count < history_len for count in per_call_counts)

    # Persisted history stays coherent: a flat list of Message objects that grew by exactly the
    # input + output of each turn (2 turns * 2 messages), with no leaked per-call summaries.
    stored = session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"]
    assert all(isinstance(m, Message) for m in stored)
    assert len(stored) == history_len + 4


async def test_harness_chat_client_middleware_execution_order(
    chat_client_base: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The harness chat-client pipeline must execute in a specific outer-to-inner order.

    Injected messages must be persisted (injection outer of per-service-call persistence) and
    compaction must run on the full persisted history (inner of persistence), all inside the
    function-invocation loop so injection can happen within the tool-calling loop. See issue #7011.

    Expected order (outermost first):
        1. Function Invocation Loop
        2. MessageInjectionMiddleware
        3. PerServiceCallHistoryPersistingMiddleware
        4. Compaction (agent ``compaction_strategy`` option, per model call)
        5. Leaf ChatClient
    """
    order: list[str] = []

    original_function_loop = FunctionInvocationLayer.get_response

    def recording_function_loop(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Fires once at the top of the run; the internal ``super().get_response`` is a different
        # bound method, so this does not re-fire per model iteration.
        order.append("function_loop")
        return original_function_loop(self, *args, **kwargs)

    original_injection = MessageInjectionMiddleware.process

    async def recording_injection(self: Any, context: Any, call_next: Any) -> None:
        order.append("message_injection")
        await original_injection(self, context, call_next)

    original_persistence = PerServiceCallHistoryPersistingMiddleware.process

    async def recording_persistence(self: Any, context: Any, call_next: Any) -> None:
        order.append("per_service_call")
        await original_persistence(self, context, call_next)

    monkeypatch.setattr(FunctionInvocationLayer, "get_response", recording_function_loop)
    monkeypatch.setattr(MessageInjectionMiddleware, "process", recording_injection)
    monkeypatch.setattr(PerServiceCallHistoryPersistingMiddleware, "process", recording_persistence)

    class _RecordingCompactionStrategy:
        async def __call__(self, messages: list[Message]) -> bool:
            order.append("compaction")
            return False

    async def recording_leaf(*, messages: Sequence[Message], options: dict[str, Any], **kwargs: Any) -> ChatResponse:
        order.append("leaf")
        return ChatResponse(messages=Message(role="assistant", contents=["ok"]))

    agent = create_harness_agent(
        client=chat_client_base,
        max_context_window_tokens=2_000,
        max_output_tokens=500,
        tokenizer=CharacterEstimatorTokenizer(),
        before_compaction_strategy=_RecordingCompactionStrategy(),
        disable_todo=True,
        disable_mode=True,
        disable_file_memory=True,
    )

    session = agent.create_session()
    with patch.object(chat_client_base, "_get_non_streaming_response", side_effect=recording_leaf):
        await agent.run("hello", session=session)

    assert order == ["function_loop", "message_injection", "per_service_call", "compaction", "leaf"]


# --- Validation Tests ---


def test_create_harness_agent_rejects_invalid_context_tokens() -> None:
    """max_context_window_tokens must be positive."""
    with pytest.raises(ValueError, match="max_context_window_tokens must be positive"):
        create_harness_agent(
            client=_FakeChatClient(),
            max_context_window_tokens=0,
            max_output_tokens=100,
        )


def test_create_harness_agent_rejects_non_positive_output_tokens() -> None:
    """max_output_tokens must be positive."""
    with pytest.raises(ValueError, match="max_output_tokens must be positive"):
        create_harness_agent(
            client=_FakeChatClient(),
            max_context_window_tokens=1000,
            max_output_tokens=0,
        )


def test_create_harness_agent_rejects_negative_output_tokens() -> None:
    """max_output_tokens must be positive."""
    with pytest.raises(ValueError, match="max_output_tokens must be positive"):
        create_harness_agent(
            client=_FakeChatClient(),
            max_context_window_tokens=1000,
            max_output_tokens=-1,
        )


def test_create_harness_agent_rejects_output_gte_context() -> None:
    """max_output_tokens must be less than max_context_window_tokens."""
    with pytest.raises(ValueError, match="max_output_tokens must be less than"):
        create_harness_agent(
            client=_FakeChatClient(),
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
    assert DEFAULT_HARNESS_INSTRUCTIONS in result  # type: ignore[operator]  # ty: ignore[unsupported-operator]
    assert "Focus on code review." in result  # type: ignore[operator]  # ty: ignore[unsupported-operator]


def test_empty_harness_instructions_uses_agent_only() -> None:
    """Empty harness_instructions should return agent instructions only."""
    result = _assemble_instructions("", "Custom only.")
    assert result == "Custom only."


# --- Identity Tests ---


def test_create_harness_agent_custom_identity() -> None:
    """Custom id, name, description should propagate."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
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
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    session = agent.create_session()
    assert isinstance(session, AgentSession)


def test_create_harness_agent_create_session_with_id() -> None:
    """create_session should accept a custom session_id."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    session = agent.create_session(session_id="custom-id")
    assert session.session_id == "custom-id"


async def test_create_harness_agent_run_returns_response() -> None:
    """agent.run() should return a response."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
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
        client=_FakeChatClient(),
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
        client=_FakeChatClient(),
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
        client=_FakeWebSearchClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    tools = agent.default_options.get("tools", [])
    assert "web_search_tool_instance" in tools


def test_create_harness_agent_disable_web_search() -> None:
    """disable_web_search=True should skip auto-adding the web search tool."""
    agent = create_harness_agent(
        client=_FakeWebSearchClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
    )
    tools = agent.default_options.get("tools", [])
    assert "web_search_tool_instance" not in tools


def test_create_harness_agent_no_web_search_when_unsupported() -> None:
    """Web search tool should NOT be added when client does not support it."""
    agent = create_harness_agent(
        client=_FakeChatClient(),
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
            client=_FakeChatClient(),
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

    def get_session(
        self,
        service_session_id: str | ServiceSessionId,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    async def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        from agent_framework import AgentResponse

        return AgentResponse(messages=[], response_id="fake-bg-response")


def test_create_harness_agent_no_background_agents_by_default() -> None:
    """No BackgroundAgentsProvider should be included when background_agents is not provided."""
    from agent_framework._harness._background_agents import BackgroundAgentsProvider

    agent = create_harness_agent(
        client=_FakeChatClient(),
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
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[bg_agent],  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[bg_agent],  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
        client=_FakeChatClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        background_agents=[],
    )
    providers = agent.context_providers or []
    assert not any(isinstance(p, BackgroundAgentsProvider) for p in providers)


# --- Shell Tool Tests ---


class _FakeShellTool:
    """Fake shell executor/tool exposing as_function()."""

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def run(self, command: str, *, timeout: float | None = None) -> ShellResult:
        return ShellResult(stdout="", stderr="", exit_code=0, duration_ms=0)

    async def __aenter__(self) -> _FakeShellTool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    def as_function(self) -> str:
        return "shell_fn"


class _FakeShellClient(_FakeChatClient):
    """Fake client that supports the shell tool."""

    def __init__(self) -> None:
        super().__init__()
        self.shell_func: Any = None

    def get_shell_tool(self, *, func: Any = None, **kwargs: Any) -> str:
        self.shell_func = func
        return "shell_tool_instance"


_requires_shell_tools = pytest.mark.skipif(
    importlib.util.find_spec("agent_framework_tools") is None,
    reason="agent-framework-tools is not installed in this environment",
)


@_requires_shell_tools
def test_create_harness_agent_adds_shell_tool_and_provider() -> None:
    """Shell tool and ShellEnvironmentProvider should be added when a shell executor is supplied."""
    from agent_framework_tools.shell import ShellEnvironmentProvider

    client = _FakeShellClient()
    agent = create_harness_agent(
        client=client,
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        shell_executor=_FakeShellTool(),
    )
    tools = agent.default_options.get("tools", [])
    assert "shell_tool_instance" in tools
    assert client.shell_func == "shell_fn"
    providers = agent.context_providers or []
    assert any(isinstance(p, ShellEnvironmentProvider) for p in providers)


@_requires_shell_tools
def test_create_harness_agent_shell_passes_custom_options() -> None:
    """Custom ShellEnvironmentProviderOptions should be forwarded to the provider."""
    from agent_framework_tools.shell import ShellEnvironmentProvider, ShellEnvironmentProviderOptions

    options = ShellEnvironmentProviderOptions(probe_tools=("git",))
    agent = create_harness_agent(
        client=_FakeShellClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
        shell_executor=_FakeShellTool(),
        shell_environment_provider_options=options,
    )
    providers = agent.context_providers or []
    provider = next(p for p in providers if isinstance(p, ShellEnvironmentProvider))
    assert provider._options is options


@_requires_shell_tools
def test_create_harness_agent_shell_skipped_when_unsupported(caplog: pytest.LogCaptureFixture) -> None:
    """When the client lacks get_shell_tool, both the tool and provider are skipped with a warning."""
    import logging

    from agent_framework_tools.shell import ShellEnvironmentProvider

    with caplog.at_level(logging.WARNING, logger="agent_framework._harness._agent"):
        agent = create_harness_agent(
            client=_FakeChatClient(),
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
            disable_web_search=True,
            shell_executor=_FakeShellTool(),
        )
    assert any("SupportsShellTool" in msg for msg in caplog.messages)
    providers = agent.context_providers or []
    assert not any(isinstance(p, ShellEnvironmentProvider) for p in providers)
    assert "tools" not in agent.default_options or not agent.default_options.get("tools")


@_requires_shell_tools
def test_create_harness_agent_no_shell_by_default() -> None:
    """No shell tool or provider should be added when shell_executor is not provided."""
    from agent_framework_tools.shell import ShellEnvironmentProvider

    agent = create_harness_agent(
        client=_FakeShellClient(),
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_web_search=True,
    )
    providers = agent.context_providers or []
    assert not any(isinstance(p, ShellEnvironmentProvider) for p in providers)


def test_create_harness_agent_shell_executor_without_as_function_raises() -> None:
    """A shell_executor lacking a callable as_function() should raise a clear TypeError."""

    class _BadExecutor:
        pass

    with pytest.raises(TypeError, match="as_function"):
        create_harness_agent(
            client=_FakeShellClient(),
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
            disable_web_search=True,
            shell_executor=_BadExecutor(),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )


def test_create_harness_agent_shell_executor_validated_before_client_check() -> None:
    """The as_function() contract is validated upfront, even when the client lacks shell support."""

    class _BadExecutor:
        pass

    with pytest.raises(TypeError, match="as_function"):
        create_harness_agent(
            client=_FakeChatClient(),
            max_context_window_tokens=128_000,
            max_output_tokens=16_384,
            disable_web_search=True,
            shell_executor=_BadExecutor(),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )


# --- Tool Approval Tests ---


def _find_tool_approval_middleware(agent: Any) -> Any:
    from agent_framework import ToolApprovalMiddleware

    for mw in agent.middleware or []:
        if isinstance(mw, ToolApprovalMiddleware):
            return mw
    return None


def test_create_harness_agent_adds_tool_approval_by_default() -> None:
    """Tool approval middleware should be wired in by default."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert _find_tool_approval_middleware(agent) is not None


def test_create_harness_agent_disable_tool_auto_approval() -> None:
    """disable_tool_auto_approval=True should omit the tool approval middleware."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_tool_auto_approval=True,
    )
    assert _find_tool_approval_middleware(agent) is None


def test_create_harness_agent_passes_auto_approval_rules() -> None:
    """auto_approval_rules should be forwarded to the tool approval middleware."""

    def _rule(content: Any) -> bool:
        return True

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        auto_approval_rules=[_rule],
    )
    middleware = _find_tool_approval_middleware(agent)
    assert middleware is not None
    assert _rule in middleware.auto_approval_rules


def test_create_harness_agent_adds_message_injection_by_default() -> None:
    """Message injection middleware should be wired in by default (like .NET UseMessageInjection)."""
    from agent_framework import MessageInjectionMiddleware

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert any(isinstance(mw, MessageInjectionMiddleware) for mw in agent.middleware or [])


def test_create_harness_agent_tool_approval_outermost_with_user_middleware() -> None:
    """Tool approval middleware should be placed first (outermost) ahead of user middleware."""
    from agent_framework import AgentMiddleware, ToolApprovalMiddleware

    class _CustomMiddleware(AgentMiddleware):
        async def process(self, context: Any, call_next: Any) -> None:
            await call_next()

    custom = _CustomMiddleware()
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        middleware=[custom],
    )
    assert agent.middleware is not None
    assert isinstance(agent.middleware[0], ToolApprovalMiddleware)
    assert custom in agent.middleware
    assert agent.middleware.index(custom) > 0


def test_create_harness_agent_disable_tool_auto_approval_preserves_user_middleware() -> None:
    """When tool approval is disabled, message injection plus user-supplied middleware remain."""
    from agent_framework import AgentMiddleware, MessageInjectionMiddleware

    class _CustomMiddleware(AgentMiddleware):
        async def process(self, context: Any, call_next: Any) -> None:
            await call_next()

    custom = _CustomMiddleware()
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_tool_auto_approval=True,
        middleware=[custom],
    )
    # Message injection is always wired in (before user middleware); tool approval is omitted.
    assert agent.middleware is not None
    assert custom in agent.middleware
    assert any(isinstance(mw, MessageInjectionMiddleware) for mw in agent.middleware)
    assert [type(mw) for mw in agent.middleware] == [MessageInjectionMiddleware, _CustomMiddleware]


def test_create_harness_agent_no_middleware_when_tool_approval_disabled_and_none() -> None:
    """Only the always-on message injection middleware remains when tool approval is disabled."""
    from agent_framework import MessageInjectionMiddleware

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        disable_tool_auto_approval=True,
    )
    assert agent.middleware is not None
    assert [type(mw) for mw in agent.middleware] == [MessageInjectionMiddleware]


# --- Loop Wiring Tests ---


def _find_loop_middleware(agent: Any) -> Any:
    from agent_framework import AgentLoopMiddleware

    for mw in agent.middleware or []:
        if isinstance(mw, AgentLoopMiddleware):
            return mw
    return None


def test_create_harness_agent_no_loop_by_default() -> None:
    """No loop middleware should be wired when loop_should_continue is not provided."""
    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )
    assert _find_loop_middleware(agent) is None


def test_create_harness_agent_wires_loop_when_should_continue_given() -> None:
    """Passing loop_should_continue should add an AgentLoopMiddleware as the outermost middleware."""
    from agent_framework import AgentLoopMiddleware

    def _should_continue(**kwargs: Any) -> bool:
        return False

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
    )
    assert agent.middleware is not None
    assert isinstance(agent.middleware[0], AgentLoopMiddleware)
    assert agent.middleware[0].should_continue is _should_continue


def test_create_harness_agent_loop_outermost_of_tool_approval_and_user_middleware() -> None:
    """The loop should sit outermost: loop, then tool approval, then user middleware."""
    from agent_framework import AgentLoopMiddleware, AgentMiddleware, ToolApprovalMiddleware

    class _CustomMiddleware(AgentMiddleware):
        async def process(self, context: Any, call_next: Any) -> None:
            await call_next()

    custom = _CustomMiddleware()

    def _should_continue(**kwargs: Any) -> bool:
        return False

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
        middleware=[custom],
    )
    assert agent.middleware is not None
    assert isinstance(agent.middleware[0], AgentLoopMiddleware)
    assert isinstance(agent.middleware[1], ToolApprovalMiddleware)
    assert agent.middleware.index(custom) > agent.middleware.index(agent.middleware[1])


def test_create_harness_agent_forwards_next_message_to_loop() -> None:
    """loop_next_message should be forwarded to the loop middleware."""

    def _should_continue(**kwargs: Any) -> bool:
        return False

    def _next_message(**kwargs: Any) -> Any:
        return "keep going"

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
        loop_next_message=_next_message,
    )
    loop = _find_loop_middleware(agent)
    assert loop is not None
    assert loop.next_message is _next_message


def test_create_harness_agent_uses_default_max_iterations_when_omitted() -> None:
    """When loop_max_iterations is omitted, the loop keeps the middleware's default cap."""
    from agent_framework._harness._loop import DEFAULT_MAX_ITERATIONS

    def _should_continue(**kwargs: Any) -> bool:
        return False

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
    )
    loop = _find_loop_middleware(agent)
    assert loop is not None
    assert loop.max_iterations == DEFAULT_MAX_ITERATIONS


def test_create_harness_agent_forwards_max_iterations_to_loop() -> None:
    """loop_max_iterations should be forwarded to the loop middleware, including None (unbounded)."""

    def _should_continue(**kwargs: Any) -> bool:
        return False

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
        loop_max_iterations=3,
    )
    loop = _find_loop_middleware(agent)
    assert loop is not None
    assert loop.max_iterations == 3

    unbounded = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_should_continue=_should_continue,
        loop_max_iterations=None,
    )
    unbounded_loop = _find_loop_middleware(unbounded)
    assert unbounded_loop is not None
    assert unbounded_loop.max_iterations is None


def test_create_harness_agent_next_message_and_max_iterations_ignored_without_should_continue() -> None:
    """Without loop_should_continue no loop is added, so loop params are simply ignored."""

    def _next_message(**kwargs: Any) -> Any:
        return "keep going"

    agent = create_harness_agent(
        client=_FakeChatClient(),  # type: ignore[arg-type]
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        loop_next_message=_next_message,
        loop_max_iterations=5,
    )
    assert _find_loop_middleware(agent) is None
