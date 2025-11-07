# Copyright (c) Microsoft. All rights reserved.

from typing import Any, cast

import pytest

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
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
        response = AgentRunResponse(messages=ChatMessage(Role.ASSISTANT, text=self._reply_text))
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
            msgs: list[ChatMessage] = r.agent_run_response.messages
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
            msgs: list[ChatMessage] = r.agent_run_response.messages
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
