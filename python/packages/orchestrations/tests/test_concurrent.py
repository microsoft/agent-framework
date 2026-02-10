# Copyright (c) Microsoft. All rights reserved.

from typing import Any, cast

import pytest
from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    WorkflowContext,
    WorkflowRunState,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework.orchestrations import ConcurrentBuilder
from typing_extensions import Never


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
        response = AgentResponse(messages=Message(role="assistant", text=self._reply_text))
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


def test_concurrent_builder_rejects_empty_participants() -> None:
    with pytest.raises(ValueError):
        ConcurrentBuilder(participants=[])


def test_concurrent_builder_rejects_duplicate_executors() -> None:
    a = _FakeAgentExec("dup", "A")
    b = _FakeAgentExec("dup", "B")  # same executor id
    with pytest.raises(ValueError):
        ConcurrentBuilder(participants=[a, b])


async def test_concurrent_default_aggregator_emits_single_user_and_assistants() -> None:
    # Three synthetic agent executors
    e1 = _FakeAgentExec("agentA", "Alpha")
    e2 = _FakeAgentExec("agentB", "Beta")
    e3 = _FakeAgentExec("agentC", "Gamma")

    wf = ConcurrentBuilder(participants=[e1, e2, e3]).build()

    completed = False
    output: list[Message] | None = None
    async for ev in wf.run("prompt: hello world", stream=True):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif ev.type == "output":
            output = cast(list[Message], ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    messages: list[Message] = output

    # Expect one user message + one assistant message per participant
    assert len(messages) == 1 + 3
    assert messages[0].role == "user"
    assert "hello world" in messages[0].text

    assistant_texts = {m.text for m in messages[1:]}
    assert assistant_texts == {"Alpha", "Beta", "Gamma"}
    assert all(m.role == "assistant" for m in messages[1:])


async def test_concurrent_custom_aggregator_callback_is_used() -> None:
    # Two synthetic agent executors for brevity
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    async def summarize(results: list[AgentExecutorResponse]) -> str:
        texts: list[str] = []
        for r in results:
            msgs: list[Message] = r.agent_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder(participants=[e1, e2]).with_aggregator(summarize).build()

    completed = False
    output: str | None = None
    async for ev in wf.run("prompt: custom", stream=True):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif ev.type == "output":
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
            msgs: list[Message] = r.agent_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder(participants=[e1, e2]).with_aggregator(summarize_sync).build()

    completed = False
    output: str | None = None
    async for ev in wf.run("prompt: custom sync", stream=True):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif ev.type == "output":
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

    wf = ConcurrentBuilder(participants=[e1, e2]).with_aggregator(summarize).build()

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
                msgs: list[Message] = r.agent_response.messages
                texts.append(msgs[-1].text if msgs else "")
            await ctx.yield_output(" & ".join(sorted(texts)))

    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    aggregator_instance = CustomAggregator(id="instance_aggregator")
    wf = ConcurrentBuilder(participants=[e1, e2]).with_aggregator(aggregator_instance).build()

    completed = False
    output: str | None = None
    async for ev in wf.run("prompt: instance test", stream=True):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif ev.type == "output":
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One & Two"


def test_concurrent_builder_rejects_multiple_calls_to_with_aggregator() -> None:
    """Test that multiple calls to .with_aggregator() raises an error."""

    def summarize(results: list[AgentExecutorResponse]) -> str:  # type: ignore[override]
        return str(len(results))

    with pytest.raises(ValueError, match=r"with_aggregator\(\) has already been called"):
        (
            ConcurrentBuilder(participants=[_FakeAgentExec("a", "A")])
            .with_aggregator(summarize)
            .with_aggregator(summarize)
        )


async def test_concurrent_checkpoint_resume_round_trip() -> None:
    storage = InMemoryCheckpointStorage()

    participants = (
        _FakeAgentExec("agentA", "Alpha"),
        _FakeAgentExec("agentB", "Beta"),
        _FakeAgentExec("agentC", "Gamma"),
    )

    wf = ConcurrentBuilder(participants=list(participants), checkpoint_storage=storage).build()

    baseline_output: list[Message] | None = None
    async for ev in wf.run("checkpoint concurrent", stream=True):
        if ev.type == "output":
            baseline_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
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
    wf_resume = ConcurrentBuilder(participants=list(resumed_participants), checkpoint_storage=storage).build()

    resumed_output: list[Message] | None = None
    async for ev in wf_resume.run(checkpoint_id=resume_checkpoint.checkpoint_id, stream=True):
        if ev.type == "output":
            resumed_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state in (
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
    wf = ConcurrentBuilder(participants=agents).build()

    baseline_output: list[Message] | None = None
    async for ev in wf.run("runtime checkpoint test", checkpoint_storage=storage, stream=True):
        if ev.type == "output":
            baseline_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
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
    wf_resume = ConcurrentBuilder(participants=resumed_agents).build()

    resumed_output: list[Message] | None = None
    async for ev in wf_resume.run(
        checkpoint_id=resume_checkpoint.checkpoint_id, checkpoint_storage=storage, stream=True
    ):
        if ev.type == "output":
            resumed_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state in (
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
        wf = ConcurrentBuilder(participants=agents, checkpoint_storage=buildtime_storage).build()

        baseline_output: list[Message] | None = None
        async for ev in wf.run("override test", checkpoint_storage=runtime_storage, stream=True):
            if ev.type == "output":
                baseline_output = ev.data  # type: ignore[assignment]
            if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
                break

        assert baseline_output is not None

        buildtime_checkpoints = await buildtime_storage.list_checkpoints()
        runtime_checkpoints = await runtime_storage.list_checkpoints()

        assert len(runtime_checkpoints) > 0, "Runtime storage should have checkpoints"
        assert len(buildtime_checkpoints) == 0, "Build-time storage should have no checkpoints when overridden"


async def test_concurrent_builder_reusable_after_build_with_participants() -> None:
    """Test that the builder can be reused to build multiple identical workflows with participants()."""
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    builder = ConcurrentBuilder(participants=[e1, e2])

    builder.build()

    assert builder._participants[0] is e1  # type: ignore
    assert builder._participants[1] is e2  # type: ignore
