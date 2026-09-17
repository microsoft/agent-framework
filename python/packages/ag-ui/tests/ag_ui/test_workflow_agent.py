# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkWorkflow wrapper behavior."""

from __future__ import annotations

from typing import Any, cast

import pytest
from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    response_handler,
)

from agent_framework_ag_ui import AgentFrameworkWorkflow


async def _run(agent: AgentFrameworkWorkflow, payload: dict[str, Any]) -> list[Any]:
    return [event async for event in agent.run(payload)]


def _interrupts_from_finished(event: Any) -> list[dict[str, Any]]:
    dumped = event.model_dump(by_alias=True, exclude_none=True)
    assert "interrupt" not in dumped
    outcome = dumped.get("outcome")
    assert isinstance(outcome, dict)
    assert outcome.get("type") == "interrupt"
    interrupts = outcome.get("interrupts")
    assert isinstance(interrupts, list)
    return cast(list[dict[str, Any]], interrupts)


async def test_workflow_wrapper_rejects_workflow_and_factory_at_once() -> None:
    """Workflow wrapper should reject ambiguous workflow source configuration."""

    @executor(id="start")
    async def start(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.yield_output("ok")  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

    workflow = WorkflowBuilder(start_executor=start).build()
    with pytest.raises(ValueError, match="workflow_factory"):
        AgentFrameworkWorkflow(workflow=workflow, workflow_factory=lambda _thread_id: workflow)


async def test_workflow_wrapper_factory_is_thread_scoped() -> None:
    """Thread-scoped workflow factories should isolate workflow instances by thread id."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"message": "Choose an option", "options": ["a", "b"]}, dict, request_id="choice")

    factory_calls: dict[str, int] = {}

    def workflow_factory(thread_id: str) -> Workflow:
        factory_calls[thread_id] = factory_calls.get(thread_id, 0) + 1
        return WorkflowBuilder(start_executor=requester).build()

    agent = AgentFrameworkWorkflow(workflow_factory=workflow_factory)

    first_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0]
    first_interrupt = _interrupts_from_finished(first_finished)
    assert first_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-a"] == 1

    second_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [],
            "resume": {"interrupts": [{"id": "choice", "value": {"selection": "a"}}]},
        },
    )
    second_types = [event.type for event in second_events]
    assert "RUN_ERROR" not in second_types
    second_finished = [event for event in second_events if event.type == "RUN_FINISHED"][0].model_dump(
        by_alias=True, exclude_none=True
    )
    assert "outcome" not in second_finished
    assert factory_calls["thread-a"] == 1

    third_events = await _run(
        agent,
        {
            "thread_id": "thread-b",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    third_finished = [event for event in third_events if event.type == "RUN_FINISHED"][0]
    third_interrupt = _interrupts_from_finished(third_finished)
    assert third_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-b"] == 1

    agent.clear_thread_workflow("thread-a")
    await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "restart"}],
        },
    )
    assert factory_calls["thread-a"] == 2


async def test_workflow_wrapper_without_workflow_raises_not_implemented() -> None:
    """Without workflow/workflow_factory, run should raise NotImplementedError."""
    agent = AgentFrameworkWorkflow()

    with pytest.raises(NotImplementedError, match="No workflow is attached"):
        _ = [event async for event in agent.run({"messages": [{"role": "user", "content": "start"}]})]


async def test_workflow_wrapper_factory_return_type_is_validated() -> None:
    """Factory outputs must be Workflow instances."""
    agent = AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: cast(Any, object()))

    with pytest.raises(TypeError, match="workflow_factory must return a Workflow instance"):
        _ = [event async for event in agent.run({"thread_id": "thread-a", "messages": []})]


# region checkpointing


class _StartExecutor(Executor):
    @handler
    async def run(self, message: Any, ctx: WorkflowContext[str]) -> None:
        del message
        await ctx.send_message("hello", target_id="middle")


class _MiddleExecutor(Executor):
    @handler
    async def process(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{message}-processed", target_id="finish")


class _FinishExecutor(Executor):
    @handler
    async def finish(self, message: str, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output(f"{message}-done")


def _build_multi_superstep_workflow(storage: InMemoryCheckpointStorage | None = None) -> Workflow:
    """Build a start -> middle -> finish workflow that creates a checkpoint per superstep."""
    start = _StartExecutor(id="start")
    middle = _MiddleExecutor(id="middle")
    finish = _FinishExecutor(id="finish")
    builder = WorkflowBuilder(max_iterations=10, start_executor=start)
    if storage is not None:
        builder = WorkflowBuilder(max_iterations=10, start_executor=start, checkpoint_storage=storage)
    return builder.add_edge(start, middle).add_edge(middle, finish).build()


async def test_workflow_run_creates_checkpoints_via_constructor_storage() -> None:
    """Configuring checkpoint_storage on the wrapper should create workflow checkpoints (parity with core)."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow, checkpoint_storage=storage)

    events = await _run(
        agent,
        {"thread_id": "thread-cp", "messages": [{"role": "user", "content": "start"}]},
    )

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types

    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    # One checkpoint per superstep boundary: at least the initial superstep plus follow-ups.
    assert len(checkpoints) >= 2


async def test_workflow_run_resumes_from_checkpoint_id() -> None:
    """A checkpoint_id in the forwarded props should restore persisted state and finish the workflow."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow(storage)
    agent = AgentFrameworkWorkflow(workflow=workflow, checkpoint_storage=storage)

    # First run: execute to completion while checkpoints are written.
    first_events = await _run(
        agent,
        {"thread_id": "thread-cp", "messages": [{"role": "user", "content": "start"}]},
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow.name),
        key=lambda checkpoint: checkpoint.timestamp,
    )
    assert checkpoints, "expected the run to create at least one checkpoint"
    # Resume from the earliest checkpoint so middle -> finish replays and re-produces output.
    resume_checkpoint_id = checkpoints[0].checkpoint_id

    # Resume on the same thread (same underlying workflow instance) from the checkpoint.
    resumed_events = await _run(
        agent,
        {
            "thread_id": "thread-cp",
            "messages": [],
            "forwarded_props": {"checkpoint_id": resume_checkpoint_id},
        },
    )

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_STARTED" in resumed_types
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types

    # The resumed run should reproduce the final assistant output ("hello-processed-done").
    resumed_text = "".join(
        getattr(event, "delta", "") for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"
    )
    assert "done" in resumed_text


async def test_workflow_run_reads_checkpoint_id_from_camelcase_forwarded_props() -> None:
    """A camelCase ``forwardedProps.checkpointId`` payload (wire format) should also resume."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow(storage)
    agent = AgentFrameworkWorkflow(workflow=workflow, checkpoint_storage=storage)

    first_events = await _run(
        agent,
        {"thread_id": "thread-cp-camel", "messages": [{"role": "user", "content": "start"}]},
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow.name),
        key=lambda checkpoint: checkpoint.timestamp,
    )
    assert checkpoints, "expected the run to create at least one checkpoint"

    resumed_events = await _run(
        agent,
        {
            "thread_id": "thread-cp-camel",
            "messages": [],
            "forwardedProps": {"checkpointId": checkpoints[0].checkpoint_id},
        },
    )
    resumed_types = [event.type for event in resumed_events]
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types


async def test_workflow_resume_without_checkpoint_storage_raises() -> None:
    """Requesting a checkpoint resume without any storage should fail loudly."""
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow)

    with pytest.raises(ValueError, match="requires checkpoint_storage"):
        await _run(
            agent,
            {
                "thread_id": "thread-cp-nostorage",
                "messages": [],
                "forwarded_props": {"checkpoint_id": "some-checkpoint"},
            },
        )


async def test_workflow_wrapper_resumes_builder_storage_without_agui_storage() -> None:
    """Builder-owned storage must round-trip through AgentFrameworkWorkflow.run() without wrapper storage."""
    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow(storage)
    # Host configures storage only on the builder; AG-UI wrapper / endpoint omit it.
    agent = AgentFrameworkWorkflow(workflow=workflow)

    first_events = await _run(
        agent,
        {"thread_id": "thread-builder-cp", "messages": [{"role": "user", "content": "start"}]},
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow.name),
        key=lambda checkpoint: checkpoint.timestamp,
    )
    assert checkpoints, "expected the builder-storage run to create at least one checkpoint"
    resume_checkpoint_id = checkpoints[0].checkpoint_id

    resume_events = await _run(
        agent,
        {
            "thread_id": "thread-builder-cp",
            "messages": [],
            "forwarded_props": {"checkpoint_id": resume_checkpoint_id},
        },
    )
    resumed_types = [event.type for event in resume_events]
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types


async def test_workflow_run_without_checkpointing_is_unchanged() -> None:
    """Existing run(input_data) calls keep working unchanged when no checkpoint args are given."""
    workflow = _build_multi_superstep_workflow()
    agent = AgentFrameworkWorkflow(workflow=workflow)

    events = await _run(agent, {"thread_id": "thread-plain", "messages": [{"role": "user", "content": "start"}]})

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types


async def test_workflow_checkpoint_only_resume_preserves_thread_snapshot() -> None:
    """A checkpoint-only resume must keep the prior stored thread snapshot, not truncate it.

    Regression test for a checkpoint-only resume (no new messages) silently replacing
    the stored AG-UI Thread Snapshot with just the newly produced output, dropping the
    earlier replayable transcript.
    """
    from agent_framework_ag_ui import InMemoryAGUIThreadSnapshotStore
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY, AGUIThreadSnapshot

    storage = InMemoryCheckpointStorage()
    workflow = _build_multi_superstep_workflow(storage)
    store = InMemoryAGUIThreadSnapshotStore()
    agent = AgentFrameworkWorkflow(workflow=workflow, snapshot_store=store, checkpoint_storage=storage)

    # Prime the workflow so a checkpoint exists to resume from.
    first_events = await _run(
        agent,
        {
            "thread_id": "thread-cp-snap",
            "run_id": "run-1",
            "messages": [{"id": "user-1", "role": "user", "content": "First question"}],
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    checkpoints = sorted(
        await storage.list_checkpoints(workflow_name=workflow.name),
        key=lambda checkpoint: checkpoint.timestamp,
    )
    assert checkpoints, "expected the primed run to create at least one checkpoint"
    # Resume from the earliest checkpoint so middle -> finish replays and re-produces output.
    resume_checkpoint_id = checkpoints[0].checkpoint_id

    # Stand in for a richer stored transcript: two prior replayable messages that a
    # checkpoint-only resume must preserve alongside the resumed output.
    await store.save(
        scope="tenant-a",
        thread_id="thread-cp-snap",
        snapshot=AGUIThreadSnapshot(
            messages=[
                {"id": "user-1", "role": "user", "content": "First question"},
                {"id": "assistant-1", "role": "assistant", "content": "Earlier reply"},
            ],
            state=None,
            interrupt=None,
        ),
    )

    # Checkpoint-only resume: no new messages, resume from the checkpoint.
    resumed_events = await _run(
        agent,
        {
            "thread_id": "thread-cp-snap",
            "run_id": "run-2",
            "messages": [],
            "forwarded_props": {"checkpoint_id": resume_checkpoint_id},
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in resumed_events]

    snapshot = await store.get(scope="tenant-a", thread_id="thread-cp-snap")
    assert snapshot is not None
    contents = [message.get("content") for message in snapshot.messages]
    # Prior transcript preserved...
    assert "First question" in contents
    assert "Earlier reply" in contents
    # ...plus the newly produced output from the resumed run.
    assert any(isinstance(content, str) and "done" in content for content in contents)


async def test_workflow_snapshot_preserves_streamed_reasoning() -> None:
    """Reasoning that streamed during a workflow run survives thread hydration.

    Regression test for workflow reasoning rendering live and then vanishing from the
    stored AG-UI Thread Snapshot, so a hydrated thread lost the intermediate output
    that the agent path retains.
    """
    from agent_framework_ag_ui import InMemoryAGUIThreadSnapshotStore
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY

    @executor(id="thinker")
    async def thinker(message: Any, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("Weighing the options...")
        await ctx.send_message("go")

    @executor(id="finalizer")
    async def finalizer(message: str, ctx: WorkflowContext[None, str]) -> None:
        await ctx.yield_output("Final answer.")

    workflow = (
        WorkflowBuilder(
            start_executor=thinker,
            output_from=[finalizer],
            intermediate_output_from=[thinker],
        )
        .add_edge(thinker, finalizer)
        .build()
    )

    store = InMemoryAGUIThreadSnapshotStore()
    agent = AgentFrameworkWorkflow(workflow=workflow, snapshot_store=store)

    events = await _run(
        agent,
        {
            "thread_id": "thread-reasoning",
            "run_id": "run-1",
            "messages": [{"id": "user-1", "role": "user", "content": "Decide"}],
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in events]

    # The reasoning really did stream ...
    reasoning_deltas = [
        event.delta  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        for event in events
        if event.type == "REASONING_MESSAGE_CONTENT"
    ]
    assert "Weighing the options..." in reasoning_deltas

    # ... and it is still there once the thread is hydrated from the snapshot.
    snapshot = await store.get(scope="tenant-a", thread_id="thread-reasoning")
    assert snapshot is not None
    reasoning_messages = [message for message in snapshot.messages if message.get("role") == "reasoning"]
    assert [message.get("content") for message in reasoning_messages] == ["Weighing the options..."]

    # The final assistant text is still preserved alongside it.
    assert any(message.get("content") == "Final answer." for message in snapshot.messages)

async def test_workflow_hitl_resume_persists_user_text_in_thread_snapshot() -> None:
    """HITL resume with messages:[] must still record the user reply in the snapshot (#8160)."""
    from agent_framework import Message

    from agent_framework_ag_ui import InMemoryAGUIThreadSnapshotStore
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY, AGUIThreadSnapshot

    class MessageRequestExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="message_request_executor")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext[Any, str]) -> None:
            del message
            await ctx.request_info({"prompt": "Need user follow-up"}, list[Message], request_id="handoff-user-input")

        @response_handler
        async def handle_user_input(
            self, original_request: dict, response: list[Message], ctx: WorkflowContext[Any, str]
        ) -> None:
            del original_request
            user_text = response[0].text if response else ""
            await ctx.yield_output(f"Captured response: {user_text}")

    storage = InMemoryCheckpointStorage()
    workflow = WorkflowBuilder(start_executor=MessageRequestExecutor()).build()
    store = InMemoryAGUIThreadSnapshotStore()
    agent = AgentFrameworkWorkflow(workflow=workflow, snapshot_store=store, checkpoint_storage=storage)

    first_events = await _run(
        agent,
        {
            "thread_id": "thread-hitl",
            "run_id": "run-1",
            "messages": [{"id": "user-1", "role": "user", "content": "start"}],
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in first_events]

    await store.save(
        scope="tenant-a",
        thread_id="thread-hitl",
        snapshot=AGUIThreadSnapshot(
            messages=[
                {"id": "user-1", "role": "user", "content": "start"},
                {"id": "assistant-1", "role": "assistant", "content": "Need more detail"},
            ],
            state=None,
            interrupt=None,
        ),
    )

    resumed_events = await _run(
        agent,
        {
            "thread_id": "thread-hitl",
            "run_id": "run-2",
            "messages": [],
            "resume": {
                "interrupts": [
                    {
                        "id": "handoff-user-input",
                        "value": [
                            {
                                "role": "user",
                                "contents": [{"type": "text", "text": "Please ship a replacement instead."}],
                            }
                        ],
                    }
                ]
            },
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in resumed_events]

    snapshot = await store.get(scope="tenant-a", thread_id="thread-hitl")
    assert snapshot is not None
    contents = [message.get("content") for message in snapshot.messages]
    assert "start" in contents
    assert any(isinstance(content, str) and "replacement" in content for content in contents)
    assert any(
        message.get("role") == "user"
        and isinstance(message.get("content"), str)
        and "replacement" in message["content"]
        for message in snapshot.messages
    )


async def test_workflow_hitl_resume_keeps_repeated_yes_on_empty_messages() -> None:
    """A second HITL 'yes' with messages:[] must not be dropped as a content duplicate."""
    from agent_framework import Message

    from agent_framework_ag_ui import InMemoryAGUIThreadSnapshotStore
    from agent_framework_ag_ui._snapshots import _SNAPSHOT_SCOPE_INPUT_KEY, AGUIThreadSnapshot

    class MessageRequestExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="message_request_executor")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext[Any, str]) -> None:
            del message
            await ctx.request_info({"prompt": "Need user follow-up"}, list[Message], request_id="handoff-user-input")

        @response_handler
        async def handle_user_input(
            self, original_request: dict, response: list[Message], ctx: WorkflowContext[Any, str]
        ) -> None:
            del original_request
            user_text = response[0].text if response else ""
            await ctx.yield_output(f"Captured response: {user_text}")

    storage = InMemoryCheckpointStorage()
    workflow = WorkflowBuilder(start_executor=MessageRequestExecutor()).build()
    store = InMemoryAGUIThreadSnapshotStore()
    agent = AgentFrameworkWorkflow(workflow=workflow, snapshot_store=store, checkpoint_storage=storage)

    await store.save(
        scope="tenant-a",
        thread_id="thread-hitl-yes",
        snapshot=AGUIThreadSnapshot(
            messages=[
                {"id": "user-1", "role": "user", "content": "start"},
                {"id": "assistant-1", "role": "assistant", "content": "confirm?"},
                {"id": "user-yes-1", "role": "user", "content": "yes"},
                {"id": "assistant-2", "role": "assistant", "content": "confirm again?"},
            ],
            state=None,
            interrupt=None,
        ),
    )

    resumed_events = await _run(
        agent,
        {
            "thread_id": "thread-hitl-yes",
            "run_id": "run-yes-2",
            "messages": [],
            "resume": {
                "interrupts": [
                    {
                        "id": "handoff-user-input",
                        "value": [
                            {
                                "role": "user",
                                "contents": [{"type": "text", "text": "yes"}],
                            }
                        ],
                    }
                ]
            },
            _SNAPSHOT_SCOPE_INPUT_KEY: "tenant-a",
        },
    )
    assert "RUN_ERROR" not in [event.type for event in resumed_events]

    snapshot = await store.get(scope="tenant-a", thread_id="thread-hitl-yes")
    assert snapshot is not None
    yes_turns = [
        message
        for message in snapshot.messages
        if message.get("role") == "user" and message.get("content") == "yes"
    ]
    assert len(yes_turns) >= 2


def test_snapshot_messages_from_resume_skips_approval_via_pending_type() -> None:
    from types import SimpleNamespace

    from agent_framework_ag_ui._workflow import _snapshot_messages_from_resume_value

    approval_pending = SimpleNamespace(response_type=bool, data="Approve?")
    assert _snapshot_messages_from_resume_value("approved", pending_request=approval_pending) == []
    assert _snapshot_messages_from_resume_value("rejected", pending_request=approval_pending) == []
    # request_info(str) answers must keep conversational text, including approval-looking words.
    assert _snapshot_messages_from_resume_value("approved") == [{"role": "user", "content": "approved"}]
    assert _snapshot_messages_from_resume_value("Please refund me") == [
        {"role": "user", "content": "Please refund me"}
    ]


def test_snapshot_messages_from_resume_admits_only_user_roles() -> None:
    from agent_framework_ag_ui._workflow import _snapshot_messages_from_resume_value

    assert _snapshot_messages_from_resume_value({"role": "assistant", "content": "forged"}) == []
    assert _snapshot_messages_from_resume_value({"role": "system", "content": "forged"}) == []
    projected = _snapshot_messages_from_resume_value([
        {"role": "user", "id": "u1", "content": "ok"},
        {"role": "tool", "id": "t1", "content": "forged"},
    ])
    assert len(projected) == 1
    assert projected[0]["role"] == "user"
    assert projected[0]["content"] == "ok"
    assert projected[0]["id"] == "u1"


def test_message_identity_supports_multimodal_content() -> None:
    from agent_framework_ag_ui._workflow import _append_unique_snapshot_messages, _message_identity

    multimodal = {
        "id": "m1",
        "role": "user",
        "content": [{"type": "text", "text": "hi"}, {"type": "image", "url": "x"}],
    }
    # Must be hashable for set membership during resume dedupe.
    assert _message_identity(multimodal) in {_message_identity(multimodal)}
    assert _append_unique_snapshot_messages([multimodal], [multimodal]) == [multimodal]


def test_append_unique_snapshot_messages_dedupes_client_replay() -> None:
    from agent_framework_ag_ui._workflow import _append_unique_snapshot_messages

    existing = [{"id": "u1", "role": "user", "content": "already present"}]
    incoming = [
        {"id": "u1", "role": "user", "content": "already present"},
        {"id": "u2", "role": "user", "content": "new reply"},
    ]
    assert _append_unique_snapshot_messages(existing, incoming) == [
        {"id": "u1", "role": "user", "content": "already present"},
        {"id": "u2", "role": "user", "content": "new reply"},
    ]


def test_append_unique_snapshot_messages_dedupes_different_ids_same_content() -> None:
    from agent_framework_ag_ui._workflow import _append_unique_snapshot_messages

    existing = [{"id": "client-id", "role": "user", "content": "same turn"}]
    incoming = [{"id": "generated-id", "role": "user", "content": "same turn"}]
    # Content fallback only applies against confirmed client-replay overlap.
    assert (
        _append_unique_snapshot_messages(
            existing,
            incoming,
            content_dedupe_against=existing,
        )
        == existing
    )


def test_append_unique_snapshot_messages_keeps_intentional_repeated_replies() -> None:
    from agent_framework_ag_ui._workflow import _append_unique_snapshot_messages

    existing = [{"id": "u0", "role": "user", "content": "hello"}]
    incoming = [
        {"id": "r1", "role": "user", "content": "repeat"},
        {"id": "r2", "role": "user", "content": "repeat"},
    ]
    merged = _append_unique_snapshot_messages(existing, incoming)
    assert [m["id"] for m in merged] == ["u0", "r1", "r2"]


def test_append_unique_snapshot_messages_keeps_second_hitl_yes_without_client_replay() -> None:
    """messages:[] HITL resumes must not collapse a later identical reply against history."""
    from agent_framework_ag_ui._workflow import _append_unique_snapshot_messages

    history = [
        {"id": "u0", "role": "user", "content": "start"},
        {"id": "a0", "role": "assistant", "content": "confirm?"},
        {"id": "u1", "role": "user", "content": "yes"},
        {"id": "a1", "role": "assistant", "content": "confirm again?"},
    ]
    second_yes = [{"id": "generated-yes-2", "role": "user", "content": "yes"}]
    merged = _append_unique_snapshot_messages(
        history,
        second_yes,
        content_dedupe_against=[],
    )
    assert [m["id"] for m in merged] == ["u0", "a0", "u1", "a1", "generated-yes-2"]
