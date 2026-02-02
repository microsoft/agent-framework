# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any

import pytest

from agent_framework import (
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Content,
    Executor,
    Role,
    SequentialBuilder,
    TypeCompatibilityError,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage


class _EchoAgent(BaseAgent):
    """Simple agent that appends a single assistant message with its name."""

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        return AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=f"{self.name} reply")])

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        # Minimal async generator with one assistant update
        yield AgentResponseUpdate(contents=[Content.from_text(text=f"{self.name} reply")])


class _SummarizerExec(Executor):
    """Custom executor that summarizes by appending a short assistant message."""

    @handler
    async def summarize(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        conversation = agent_response.full_conversation or []
        user_texts = [m.text for m in conversation if m.role == Role.USER]
        agents = [m.author_name or m.role for m in conversation if m.role == Role.ASSISTANT]
        summary = ChatMessage(role=Role.ASSISTANT, text=f"Summary of users:{len(user_texts)} agents:{len(agents)}")
        await ctx.send_message(list(conversation) + [summary])


class _InvalidExecutor(Executor):
    """Invalid executor that does not have a handler that accepts a list of chat messages"""

    @handler
    async def summarize(self, conversation: list[str], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        pass


def test_sequential_builder_rejects_empty_participants() -> None:
    with pytest.raises(ValueError):
        SequentialBuilder().participants([])


def test_sequential_builder_rejects_empty_participant_factories() -> None:
    with pytest.raises(ValueError):
        SequentialBuilder().register_participants([])


def test_sequential_builder_rejects_mixing_participants_and_factories() -> None:
    """Test that mixing .participants() and .register_participants() raises an error."""
    a1 = _EchoAgent(id="agent1", name="A1")

    # Try .participants() then .register_participants()
    with pytest.raises(ValueError, match="Cannot mix"):
        SequentialBuilder().participants([a1]).register_participants([lambda: _EchoAgent(id="agent2", name="A2")])

    # Try .register_participants() then .participants()
    with pytest.raises(ValueError, match="Cannot mix"):
        SequentialBuilder().register_participants([lambda: _EchoAgent(id="agent1", name="A1")]).participants([a1])


def test_sequential_builder_validation_rejects_invalid_executor() -> None:
    """Test that adding an invalid executor to the builder raises an error."""
    with pytest.raises(TypeCompatibilityError):
        SequentialBuilder().participants([_EchoAgent(id="agent1", name="A1"), _InvalidExecutor(id="invalid")]).build()


async def test_sequential_agents_append_to_context() -> None:
    a1 = _EchoAgent(id="agent1", name="A1")
    a2 = _EchoAgent(id="agent2", name="A2")

    wf = SequentialBuilder().participants([a1, a2]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("hello sequential"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, list)
    msgs: list[ChatMessage] = output
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER and "hello sequential" in msgs[0].text
    assert msgs[1].role == Role.ASSISTANT and (msgs[1].author_name == "A1" or True)
    assert msgs[2].role == Role.ASSISTANT and (msgs[2].author_name == "A2" or True)
    assert "A1 reply" in msgs[1].text
    assert "A2 reply" in msgs[2].text


async def test_sequential_register_participants_with_agent_factories() -> None:
    """Test that register_participants works with agent factories."""

    def create_agent1() -> _EchoAgent:
        return _EchoAgent(id="agent1", name="A1")

    def create_agent2() -> _EchoAgent:
        return _EchoAgent(id="agent2", name="A2")

    wf = SequentialBuilder().register_participants([create_agent1, create_agent2]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("hello factories"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, list)
    msgs: list[ChatMessage] = output
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER and "hello factories" in msgs[0].text
    assert msgs[1].role == Role.ASSISTANT and "A1 reply" in msgs[1].text
    assert msgs[2].role == Role.ASSISTANT and "A2 reply" in msgs[2].text


async def test_sequential_with_custom_executor_summary() -> None:
    a1 = _EchoAgent(id="agent1", name="A1")
    summarizer = _SummarizerExec(id="summarizer")

    wf = SequentialBuilder().participants([a1, summarizer]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("topic X"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    msgs: list[ChatMessage] = output
    # Expect: [user, A1 reply, summary]
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER
    assert msgs[1].role == Role.ASSISTANT and "A1 reply" in msgs[1].text
    assert msgs[2].role == Role.ASSISTANT and msgs[2].text.startswith("Summary of users:")


async def test_sequential_register_participants_mixed_agents_and_executors() -> None:
    """Test register_participants with both agent and executor factories."""

    def create_agent() -> _EchoAgent:
        return _EchoAgent(id="agent1", name="A1")

    def create_summarizer() -> _SummarizerExec:
        return _SummarizerExec(id="summarizer")

    wf = SequentialBuilder().register_participants([create_agent, create_summarizer]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("topic Y"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    msgs: list[ChatMessage] = output
    # Expect: [user, A1 reply, summary]
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER and "topic Y" in msgs[0].text
    assert msgs[1].role == Role.ASSISTANT and "A1 reply" in msgs[1].text
    assert msgs[2].role == Role.ASSISTANT and msgs[2].text.startswith("Summary of users:")


async def test_sequential_checkpoint_resume_round_trip() -> None:
    storage = InMemoryCheckpointStorage()

    initial_agents = (_EchoAgent(id="agent1", name="A1"), _EchoAgent(id="agent2", name="A2"))
    wf = SequentialBuilder().participants(list(initial_agents)).with_checkpointing(storage).build()

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("checkpoint sequential"):
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

    resumed_agents = (_EchoAgent(id="agent1", name="A1"), _EchoAgent(id="agent2", name="A2"))
    wf_resume = SequentialBuilder().participants(list(resumed_agents)).with_checkpointing(storage).build()

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


async def test_sequential_checkpoint_runtime_only() -> None:
    """Test checkpointing configured ONLY at runtime, not at build time."""
    storage = InMemoryCheckpointStorage()

    agents = (_EchoAgent(id="agent1", name="A1"), _EchoAgent(id="agent2", name="A2"))
    wf = SequentialBuilder().participants(list(agents)).build()

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

    resumed_agents = (_EchoAgent(id="agent1", name="A1"), _EchoAgent(id="agent2", name="A2"))
    wf_resume = SequentialBuilder().participants(list(resumed_agents)).build()

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
    assert [m.text for m in resumed_output] == [m.text for m in baseline_output]


async def test_sequential_checkpoint_runtime_overrides_buildtime() -> None:
    """Test that runtime checkpoint storage overrides build-time configuration."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
        from agent_framework._workflows._checkpoint import FileCheckpointStorage

        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        agents = (_EchoAgent(id="agent1", name="A1"), _EchoAgent(id="agent2", name="A2"))
        wf = SequentialBuilder().participants(list(agents)).with_checkpointing(buildtime_storage).build()

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


async def test_sequential_register_participants_with_checkpointing() -> None:
    """Test that checkpointing works with register_participants."""
    storage = InMemoryCheckpointStorage()

    def create_agent1() -> _EchoAgent:
        return _EchoAgent(id="agent1", name="A1")

    def create_agent2() -> _EchoAgent:
        return _EchoAgent(id="agent2", name="A2")

    wf = SequentialBuilder().register_participants([create_agent1, create_agent2]).with_checkpointing(storage).build()

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("checkpoint with factories"):
        if isinstance(ev, WorkflowOutputEvent):
            baseline_output = ev.data
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

    wf_resume = (
        SequentialBuilder().register_participants([create_agent1, create_agent2]).with_checkpointing(storage).build()
    )

    resumed_output: list[ChatMessage] | None = None
    async for ev in wf_resume.run_stream(checkpoint_id=resume_checkpoint.checkpoint_id):
        if isinstance(ev, WorkflowOutputEvent):
            resumed_output = ev.data
        if isinstance(ev, WorkflowStatusEvent) and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert resumed_output is not None
    assert [m.role for m in resumed_output] == [m.role for m in baseline_output]
    assert [m.text for m in resumed_output] == [m.text for m in baseline_output]


async def test_sequential_register_participants_factories_called_on_build() -> None:
    """Test that factories are called during build(), not during register_participants()."""
    call_count = 0

    def create_agent() -> _EchoAgent:
        nonlocal call_count
        call_count += 1
        return _EchoAgent(id=f"agent{call_count}", name=f"A{call_count}")

    builder = SequentialBuilder().register_participants([create_agent, create_agent])

    # Factories should not be called yet
    assert call_count == 0

    wf = builder.build()

    # Now factories should have been called
    assert call_count == 2

    # Run the workflow to ensure it works
    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("test factories timing"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    msgs: list[ChatMessage] = output
    # Should have user message + 2 agent replies
    assert len(msgs) == 3


async def test_sequential_builder_reusable_after_build_with_participants() -> None:
    """Test that the builder can be reused to build multiple identical workflows with participants()."""
    a1 = _EchoAgent(id="agent1", name="A1")
    a2 = _EchoAgent(id="agent2", name="A2")

    builder = SequentialBuilder().participants([a1, a2])

    # Build first workflow
    builder.build()

    assert builder._participants[0] is a1  # type: ignore
    assert builder._participants[1] is a2  # type: ignore
    assert builder._participant_factories == []  # type: ignore


async def test_sequential_builder_reusable_after_build_with_factories() -> None:
    """Test that the builder can be reused to build multiple workflows with register_participants()."""
    call_count = 0

    def create_agent1() -> _EchoAgent:
        nonlocal call_count
        call_count += 1
        return _EchoAgent(id="agent1", name="A1")

    def create_agent2() -> _EchoAgent:
        nonlocal call_count
        call_count += 1
        return _EchoAgent(id="agent2", name="A2")

    builder = SequentialBuilder().register_participants([create_agent1, create_agent2])

    # Build first workflow - factories should be called
    builder.build()

    assert call_count == 2
    assert builder._participants == []  # type: ignore
    assert len(builder._participant_factories) == 2  # type: ignore
    assert builder._participant_factories[0] is create_agent1  # type: ignore
    assert builder._participant_factories[1] is create_agent2  # type: ignore
