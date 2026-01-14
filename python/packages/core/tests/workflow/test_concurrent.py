# Copyright (c) Microsoft. All rights reserved.

from typing import Any, cast

import pytest
from typing_extensions import Never

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    Role,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage


class _FakeAgentExec(Executor):
    """Test executor that mimics an agent by emitting an AgentExecutorResponse.

    It takes the incoming AgentExecutorRequest, produces a single assistant message
    with the configured reply text, and sends an AgentExecutorResponse that includes
    full_conversation (the original user prompt followed by the assistant message).
    """

    def __init__(self, id: str, reply_text: str) -> None:
        super().__init__(id)
        self._reply_text = reply_text

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = AgentResponse(messages=ChatMessage(Role.ASSISTANT, text=self._reply_text))
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


def test_concurrent_builder_rejects_empty_participants() -> None:
    with pytest.raises(ValueError):
        ConcurrentBuilder().participants([])


def test_concurrent_builder_rejects_duplicate_executors() -> None:
    a = _FakeAgentExec("dup", "A")
    b = _FakeAgentExec("dup", "B")  # same executor id
    with pytest.raises(ValueError):
        ConcurrentBuilder().participants([a, b])


def test_concurrent_builder_rejects_duplicate_executors_from_factories() -> None:
    """Test that duplicate executor IDs from factories are detected at build time."""

    def create_dup1() -> Executor:
        return _FakeAgentExec("dup", "A")

    def create_dup2() -> Executor:
        return _FakeAgentExec("dup", "B")  # same executor id

    builder = ConcurrentBuilder().register_participants([create_dup1, create_dup2])
    with pytest.raises(ValueError, match="Duplicate executor ID 'dup' detected in workflow."):
        builder.build()


def test_concurrent_builder_rejects_mixed_participants_and_factories() -> None:
    """Test that mixing .participants() and .register_participants() raises an error."""
    # Case 1: participants first, then register_participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        (
            ConcurrentBuilder()
            .participants([_FakeAgentExec("a", "A")])
            .register_participants([lambda: _FakeAgentExec("b", "B")])
        )

    # Case 2: register_participants first, then participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        (
            ConcurrentBuilder()
            .register_participants([lambda: _FakeAgentExec("a", "A")])
            .participants([_FakeAgentExec("b", "B")])
        )


def test_concurrent_builder_rejects_multiple_calls_to_participants() -> None:
    """Test that multiple calls to .participants() raises an error."""
    with pytest.raises(ValueError, match=r"participants\(\) has already been called"):
        (ConcurrentBuilder().participants([_FakeAgentExec("a", "A")]).participants([_FakeAgentExec("b", "B")]))


def test_concurrent_builder_rejects_multiple_calls_to_register_participants() -> None:
    """Test that multiple calls to .register_participants() raises an error."""
    with pytest.raises(ValueError, match=r"register_participants\(\) has already been called"):
        (
            ConcurrentBuilder()
            .register_participants([lambda: _FakeAgentExec("a", "A")])
            .register_participants([lambda: _FakeAgentExec("b", "B")])
        )


async def test_concurrent_default_aggregator_emits_single_user_and_assistants() -> None:
    # Three synthetic agent executors
    e1 = _FakeAgentExec("agentA", "Alpha")
    e2 = _FakeAgentExec("agentB", "Beta")
    e3 = _FakeAgentExec("agentC", "Gamma")

    wf = ConcurrentBuilder().participants([e1, e2, e3]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("prompt: hello world"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(list[ChatMessage], ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    messages: list[ChatMessage] = output

    # Expect one user message + one assistant message per participant
    assert len(messages) == 1 + 3
    assert messages[0].role == Role.USER
    assert "hello world" in messages[0].text

    assistant_texts = {m.text for m in messages[1:]}
    assert assistant_texts == {"Alpha", "Beta", "Gamma"}
    assert all(m.role == Role.ASSISTANT for m in messages[1:])


async def test_concurrent_custom_aggregator_callback_is_used() -> None:
    # Two synthetic agent executors for brevity
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    async def summarize(results: list[AgentExecutorResponse]) -> str:
        texts: list[str] = []
        for r in results:
            msgs: list[ChatMessage] = r.agent_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: custom"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    # Custom aggregator returns a string payload
    assert isinstance(output, str)
    assert output == "One | Two"


async def test_concurrent_custom_aggregator_sync_callback_is_used() -> None:
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    # Sync callback with ctx parameter (should run via asyncio.to_thread)
    def summarize_sync(results: list[AgentExecutorResponse], _ctx: WorkflowContext[Any]) -> str:  # type: ignore[unused-argument]
        texts: list[str] = []
        for r in results:
            msgs: list[ChatMessage] = r.agent_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize_sync).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: custom sync"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One | Two"


def test_concurrent_custom_aggregator_uses_callback_name_for_id() -> None:
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    def summarize(results: list[AgentExecutorResponse]) -> str:  # type: ignore[override]
        return str(len(results))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize).build()

    assert "summarize" in wf.executors
    aggregator = wf.executors["summarize"]
    assert aggregator.id == "summarize"


async def test_concurrent_with_aggregator_executor_instance() -> None:
    """Test with_aggregator using an Executor instance (not factory)."""

    class CustomAggregator(Executor):
        @handler
        async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
            texts: list[str] = []
            for r in results:
                msgs: list[ChatMessage] = r.agent_response.messages
                texts.append(msgs[-1].text if msgs else "")
            await ctx.yield_output(" & ".join(sorted(texts)))

    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    aggregator_instance = CustomAggregator(id="instance_aggregator")
    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(aggregator_instance).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: instance test"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One & Two"


async def test_concurrent_with_aggregator_executor_factory() -> None:
    """Test with_aggregator using an Executor factory."""

    class CustomAggregator(Executor):
        @handler
        async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
            texts: list[str] = []
            for r in results:
                msgs: list[ChatMessage] = r.agent_response.messages
                texts.append(msgs[-1].text if msgs else "")
            await ctx.yield_output(" | ".join(sorted(texts)))

    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    wf = (
        ConcurrentBuilder()
        .participants([e1, e2])
        .register_aggregator(lambda: CustomAggregator(id="custom_aggregator"))
        .build()
    )

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: factory test"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One | Two"


async def test_concurrent_with_aggregator_executor_factory_with_default_id() -> None:
    """Test with_aggregator using an Executor class directly as factory (with default __init__ parameters)."""

    class CustomAggregator(Executor):
        def __init__(self, id: str = "default_aggregator") -> None:
            super().__init__(id)

        @handler
        async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
            texts: list[str] = []
            for r in results:
                msgs: list[ChatMessage] = r.agent_response.messages
                texts.append(msgs[-1].text if msgs else "")
            await ctx.yield_output(" | ".join(sorted(texts)))

    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    wf = ConcurrentBuilder().participants([e1, e2]).register_aggregator(CustomAggregator).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: factory test"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One | Two"


def test_concurrent_builder_rejects_multiple_calls_to_with_aggregator() -> None:
    """Test that multiple calls to .with_aggregator() raises an error."""

    def summarize(results: list[AgentExecutorResponse]) -> str:  # type: ignore[override]
        return str(len(results))

    with pytest.raises(ValueError, match=r"with_aggregator\(\) has already been called"):
        (ConcurrentBuilder().with_aggregator(summarize).with_aggregator(summarize))


def test_concurrent_builder_rejects_multiple_calls_to_register_aggregator() -> None:
    """Test that multiple calls to .register_aggregator() raises an error."""

    class CustomAggregator(Executor):
        pass

    with pytest.raises(ValueError, match=r"register_aggregator\(\) has already been called"):
        (
            ConcurrentBuilder()
            .register_aggregator(lambda: CustomAggregator(id="agg1"))
            .register_aggregator(lambda: CustomAggregator(id="agg2"))
        )


async def test_concurrent_checkpoint_resume_round_trip() -> None:
    storage = InMemoryCheckpointStorage()

    participants = (
        _FakeAgentExec("agentA", "Alpha"),
        _FakeAgentExec("agentB", "Beta"),
        _FakeAgentExec("agentC", "Gamma"),
    )

    wf = ConcurrentBuilder().participants(list(participants)).with_checkpointing(storage).build()

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("checkpoint concurrent"):
        if isinstance(ev, WorkflowOutputEvent):
            baseline_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            break

    assert baseline_output is not None

    checkpoints = await storage.list_checkpoints()
    assert checkpoints
    checkpoints.sort(key=lambda cp: cp.timestamp)
    resume_checkpoint = next(
        (cp for cp in checkpoints if (cp.metadata or {}).get("checkpoint_type") == "superstep"),
        checkpoints[-1],
    )

    resumed_participants = (
        _FakeAgentExec("agentA", "Alpha"),
        _FakeAgentExec("agentB", "Beta"),
        _FakeAgentExec("agentC", "Gamma"),
    )
    wf_resume = ConcurrentBuilder().participants(list(resumed_participants)).with_checkpointing(storage).build()

    resumed_output: list[ChatMessage] | None = None
    async for ev in wf_resume.run_stream(checkpoint_id=resume_checkpoint.checkpoint_id):
        if isinstance(ev, WorkflowOutputEvent):
            resumed_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert resumed_output is not None
    assert [m.role for m in resumed_output] == [m.role for m in baseline_output]
    assert [m.text for m in resumed_output] == [m.text for m in baseline_output]


async def test_concurrent_checkpoint_runtime_only() -> None:
    """Test checkpointing configured ONLY at runtime, not at build time."""
    storage = InMemoryCheckpointStorage()

    agents = [_FakeAgentExec(id="agent1", reply_text="A1"), _FakeAgentExec(id="agent2", reply_text="A2")]
    wf = ConcurrentBuilder().participants(agents).build()

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("runtime checkpoint test", checkpoint_storage=storage):
        if isinstance(ev, WorkflowOutputEvent):
            baseline_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            break

    assert baseline_output is not None

    checkpoints = await storage.list_checkpoints()
    assert checkpoints
    checkpoints.sort(key=lambda cp: cp.timestamp)

    resume_checkpoint = next(
        (cp for cp in checkpoints if (cp.metadata or {}).get("checkpoint_type") == "superstep"),
        checkpoints[-1],
    )

    resumed_agents = [_FakeAgentExec(id="agent1", reply_text="A1"), _FakeAgentExec(id="agent2", reply_text="A2")]
    wf_resume = ConcurrentBuilder().participants(resumed_agents).build()

    resumed_output: list[ChatMessage] | None = None
    async for ev in wf_resume.run_stream(checkpoint_id=resume_checkpoint.checkpoint_id, checkpoint_storage=storage):
        if isinstance(ev, WorkflowOutputEvent):
            resumed_output = ev.data  # type: ignore[assignment]
        if isinstance(ev, WorkflowStatusEvent) and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert resumed_output is not None
    assert [m.role for m in resumed_output] == [m.role for m in baseline_output]


async def test_concurrent_checkpoint_runtime_overrides_buildtime() -> None:
    """Test that runtime checkpoint storage overrides build-time configuration."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
        from agent_framework._workflows._checkpoint import FileCheckpointStorage

        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        agents = [_FakeAgentExec(id="agent1", reply_text="A1"), _FakeAgentExec(id="agent2", reply_text="A2")]
        wf = ConcurrentBuilder().participants(agents).with_checkpointing(buildtime_storage).build()

        baseline_output: list[ChatMessage] | None = None
        async for ev in wf.run_stream("override test", checkpoint_storage=runtime_storage):
            if isinstance(ev, WorkflowOutputEvent):
                baseline_output = ev.data  # type: ignore[assignment]
            if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
                break

        assert baseline_output is not None

        buildtime_checkpoints = await buildtime_storage.list_checkpoints()
        runtime_checkpoints = await runtime_storage.list_checkpoints()

        assert len(runtime_checkpoints) > 0, "Runtime storage should have checkpoints"
        assert len(buildtime_checkpoints) == 0, "Build-time storage should have no checkpoints when overridden"


def test_concurrent_builder_rejects_empty_participant_factories() -> None:
    with pytest.raises(ValueError):
        ConcurrentBuilder().register_participants([])


async def test_concurrent_builder_reusable_after_build_with_participants() -> None:
    """Test that the builder can be reused to build multiple identical workflows with participants()."""
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    builder = ConcurrentBuilder().participants([e1, e2])

    builder.build()

    assert builder._participants[0] is e1  # type: ignore
    assert builder._participants[1] is e2  # type: ignore
    assert builder._participant_factories == []  # type: ignore


async def test_concurrent_builder_reusable_after_build_with_factories() -> None:
    """Test that the builder can be reused to build multiple workflows with register_participants()."""
    call_count = 0

    def create_agent_executor_a() -> Executor:
        nonlocal call_count
        call_count += 1
        return _FakeAgentExec("agentA", "One")

    def create_agent_executor_b() -> Executor:
        nonlocal call_count
        call_count += 1
        return _FakeAgentExec("agentB", "Two")

    builder = ConcurrentBuilder().register_participants([create_agent_executor_a, create_agent_executor_b])

    # Build the first workflow
    wf1 = builder.build()

    assert builder._participants == []  # type: ignore
    assert len(builder._participant_factories) == 2  # type: ignore
    assert call_count == 2

    # Build the second workflow
    wf2 = builder.build()
    assert call_count == 4

    # Verify that the two workflows have different executor instances
    assert wf1.executors["agentA"] is not wf2.executors["agentA"]
    assert wf1.executors["agentB"] is not wf2.executors["agentB"]


async def test_concurrent_with_register_participants() -> None:
    """Test workflow creation using register_participants with factories."""

    def create_agent1() -> Executor:
        return _FakeAgentExec("agentA", "Alpha")

    def create_agent2() -> Executor:
        return _FakeAgentExec("agentB", "Beta")

    def create_agent3() -> Executor:
        return _FakeAgentExec("agentC", "Gamma")

    wf = ConcurrentBuilder().register_participants([create_agent1, create_agent2, create_agent3]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("test prompt"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(list[ChatMessage], ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    messages: list[ChatMessage] = output

    # Expect one user message + one assistant message per participant
    assert len(messages) == 1 + 3
    assert messages[0].role == Role.USER
    assert "test prompt" in messages[0].text

    assistant_texts = {m.text for m in messages[1:]}
    assert assistant_texts == {"Alpha", "Beta", "Gamma"}
    assert all(m.role == Role.ASSISTANT for m in messages[1:])
