# Copyright (c) Microsoft. All rights reserved.

"""Workflow wrapper for AG-UI protocol compatibility."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any, cast

from ag_ui.core import (
    BaseEvent,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import CheckpointID, CheckpointStorage, Workflow, WorkflowCheckpoint
from agent_framework._telemetry import mark_feature_used

from ._feature_usage import FeatureIndex
from ._message_adapters import agui_messages_to_snapshot_format
from ._run_common import (
    _cancelled_resume_interrupt_ids,
    _extract_resume_payload,
    _normalize_resume_interrupts,
    _reconstruct_messages_from_thread_snapshot,
)
from ._snapshot_session import ThreadSnapshotSession, _event_messages_to_snapshot_dicts
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshot,
    AGUIThreadSnapshotStore,
)
from ._utils import generate_event_id, make_json_safe
from ._workflow_run import _pending_request_events, run_workflow_stream  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)

WorkflowFactory = Callable[[str], Workflow]
WorkflowRequestOwner = tuple[str | None, str | None]

_REQUEST_OWNER_ATTRIBUTE = "_ag_ui_request_owner"
_CHECKPOINT_REQUEST_OWNER_KEY = "ag_ui_workflow_request_owner"


def _checkpoint_id_from_input(input_data: dict[str, Any]) -> str | None:
    """Read an optional checkpoint id to resume from out of the AG-UI forwarded props."""
    forwarded_props = input_data.get("forwarded_props") or input_data.get("forwardedProps")
    if not isinstance(forwarded_props, dict):
        return None
    checkpoint_id = forwarded_props.get("checkpoint_id") or forwarded_props.get("checkpointId")
    if checkpoint_id is None:
        return None
    return str(checkpoint_id)


def _checkpoint_request_owner(metadata: dict[str, Any]) -> WorkflowRequestOwner | None:
    """Read AG-UI workflow request ownership from checkpoint metadata."""
    raw_owner = metadata.get(_CHECKPOINT_REQUEST_OWNER_KEY)
    if not isinstance(raw_owner, dict):
        return None
    snapshot_scope = raw_owner.get("snapshot_scope")
    thread_id = raw_owner.get("thread_id")
    if snapshot_scope is not None and not isinstance(snapshot_scope, str):
        return None
    if thread_id is not None and not isinstance(thread_id, str):
        return None
    return snapshot_scope, thread_id


class _OwnedWorkflowCheckpointStorage:
    """Attach one AG-UI request owner to checkpoints in their original save."""

    def __init__(self, storage: CheckpointStorage, owner: WorkflowRequestOwner) -> None:
        self._storage = storage
        self._owner = owner

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint with ownership for any pending request occurrences."""
        checkpoint.metadata = dict(checkpoint.metadata)
        checkpoint.metadata[_CHECKPOINT_REQUEST_OWNER_KEY] = {
            "snapshot_scope": self._owner[0],
            "thread_id": self._owner[1],
        }
        return await self._storage.save(checkpoint)

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint from the underlying store."""
        return await self._storage.load(checkpoint_id)

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoints from the underlying store."""
        return await self._storage.list_checkpoints(workflow_name=workflow_name)

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint from the underlying store."""
        return await self._storage.delete(checkpoint_id)

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint from the underlying store."""
        return await self._storage.get_latest(workflow_name=workflow_name)

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs from the underlying store."""
        return await self._storage.list_checkpoint_ids(workflow_name=workflow_name)


class _WorkflowSnapshotBuilder:
    """Capture replayable workflow protocol output without retaining raw events."""

    def __init__(self, raw_messages: list[dict[str, Any]]) -> None:
        self._synthesized_messages = agui_messages_to_snapshot_format(raw_messages)
        self._emitted_messages: list[dict[str, Any]] | None = None
        self._open_text_message: dict[str, Any] | None = None
        self._tool_call_message: dict[str, Any] | None = None
        self._tool_calls_by_id: dict[str, dict[str, Any]] = {}
        self.state: dict[str, Any] | None = None
        self.interrupt: list[dict[str, Any]] | None = None

    def observe(self, event: BaseEvent) -> None:
        """Fold one replayable AG-UI event into the latest snapshot state."""
        if isinstance(event, StateSnapshotEvent):
            state = make_json_safe(event.snapshot)
            if isinstance(state, dict):
                self.state = cast(dict[str, Any], state)
            return

        if isinstance(event, MessagesSnapshotEvent):
            self._emitted_messages = _event_messages_to_snapshot_dicts(list(event.messages))
            return

        if isinstance(event, RunFinishedEvent):
            outcome = getattr(event, "outcome", None)
            interrupt = (
                make_json_safe(getattr(outcome, "interrupts", None))
                if getattr(outcome, "type", None) == "interrupt"
                else None
            )
            if isinstance(interrupt, list):
                self.interrupt = [cast(dict[str, Any], item) for item in interrupt if isinstance(item, dict)]
            return

        if self._emitted_messages is not None:
            return

        if isinstance(event, TextMessageStartEvent):
            self._observe_text_start(event)
        elif isinstance(event, TextMessageContentEvent):
            self._observe_text_content(event)
        elif isinstance(event, TextMessageEndEvent):
            self._observe_text_end(event)
        elif isinstance(event, ToolCallStartEvent):
            self._observe_tool_call_start(event)
        elif isinstance(event, ToolCallArgsEvent):
            self._observe_tool_call_args(event)
        elif isinstance(event, ToolCallResultEvent):
            self._observe_tool_call_result(event)

    def build(self) -> AGUIThreadSnapshot:
        """Return the replayable thread snapshot."""
        self._flush_open_text_message()
        messages = self._emitted_messages if self._emitted_messages is not None else self._synthesized_messages
        return AGUIThreadSnapshot(messages=messages, state=self.state, interrupt=self.interrupt)

    def _observe_text_start(self, event: TextMessageStartEvent) -> None:
        if self._open_text_message is not None and self._open_text_message.get("id") != event.message_id:
            self._flush_open_text_message()
        self._open_text_message = {"id": event.message_id, "role": event.role, "content": ""}

    def _observe_text_content(self, event: TextMessageContentEvent) -> None:
        if self._open_text_message is None or self._open_text_message.get("id") != event.message_id:
            self._open_text_message = {"id": event.message_id, "role": "assistant", "content": ""}
        self._open_text_message["content"] = f"{self._open_text_message.get('content', '')}{event.delta}"

    def _observe_text_end(self, event: TextMessageEndEvent) -> None:
        if self._open_text_message is None or self._open_text_message.get("id") != event.message_id:
            return
        self._flush_open_text_message()

    def _observe_tool_call_start(self, event: ToolCallStartEvent) -> None:
        parent_message_id = event.parent_message_id
        if (
            self._open_text_message is not None
            and parent_message_id is not None
            and self._open_text_message.get("id") == parent_message_id
            and self._open_text_message.get("content")
        ):
            self._open_text_message["id"] = generate_event_id()
        self._flush_open_text_message()
        if self._tool_call_message is None or (
            parent_message_id is not None and self._tool_call_message.get("id") != parent_message_id
        ):
            self._tool_call_message = {
                "id": parent_message_id or generate_event_id(),
                "role": "assistant",
                "tool_calls": [],
            }
            self._synthesized_messages.append(self._tool_call_message)

        tool_call = {
            "id": event.tool_call_id,
            "type": "function",
            "function": {"name": event.tool_call_name, "arguments": ""},
        }
        cast(list[dict[str, Any]], self._tool_call_message["tool_calls"]).append(tool_call)
        self._tool_calls_by_id[event.tool_call_id] = tool_call

    def _observe_tool_call_args(self, event: ToolCallArgsEvent) -> None:
        tool_call = self._tool_calls_by_id.get(event.tool_call_id)
        if tool_call is None:
            return
        function_payload = cast(dict[str, Any], tool_call["function"])
        function_payload["arguments"] = f"{function_payload.get('arguments', '')}{event.delta}"

    def _observe_tool_call_result(self, event: ToolCallResultEvent) -> None:
        self._synthesized_messages.append(
            {
                "id": event.message_id,
                "role": "tool",
                "toolCallId": event.tool_call_id,
                "content": event.content,
            }
        )
        # A result closes the current tool-call group; later tool calls start a new
        # assistant message so replayed transcripts keep results adjacent to their
        # tool_calls message, which provider APIs require.
        self._tool_call_message = None

    def _flush_open_text_message(self) -> None:
        if self._open_text_message is None:
            return
        if self._open_text_message.get("content"):
            self._synthesized_messages.append(self._open_text_message)
            # Text between tool calls closes the current tool-call group as well.
            self._tool_call_message = None
        self._open_text_message = None


class AgentFrameworkWorkflow:
    """Base AG-UI workflow wrapper.

    Can wrap a native ``Workflow`` or be subclassed for custom ``run`` behavior.
    """

    def __init__(
        self,
        workflow: Workflow | None = None,
        *,
        workflow_factory: WorkflowFactory | None = None,
        name: str | None = None,
        description: str | None = None,
        snapshot_store: AGUIThreadSnapshotStore | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        """Initialize the AG-UI workflow wrapper.

        Args:
            workflow: Optional workflow instance to expose.
            workflow_factory: Optional factory for thread-scoped workflow instances.
            name: Optional workflow name.
            description: Optional workflow description.
            snapshot_store: Optional AG-UI Thread Snapshot store. Snapshot persistence remains inactive unless
                endpoint setup also provides an explicit Snapshot Scope resolver.
            checkpoint_storage: Optional workflow checkpoint storage. When provided, each run
                creates a checkpoint at the end of every superstep (matching
                ``agent_framework.Workflow.run(checkpoint_storage=...)``), and a run may resume
                from a persisted checkpoint by supplying its id in the AG-UI forwarded props
                (``forwarded_props: {"checkpoint_id": ...}``). Required for checkpoint resume.
        """
        if workflow is not None and workflow_factory is not None:
            raise ValueError("Pass either workflow= or workflow_factory=, not both.")

        self.workflow = workflow
        self._workflow_factory = workflow_factory
        # Cache keyed by (snapshot_scope, thread_id): the Snapshot Scope is the
        # authorization boundary for both snapshots and in-memory workflow_factory
        # instances, so the same thread id under different scopes must never share
        # mutable workflow state.
        self._workflow_by_thread: dict[tuple[str | None, str], Workflow] = {}
        self.name = name if name is not None else getattr(workflow, "name", "workflow")
        self.description = description if description is not None else getattr(workflow, "description", "")
        self.snapshot_store = snapshot_store
        self.checkpoint_storage = checkpoint_storage

    @staticmethod
    def _thread_id_from_input(input_data: dict[str, Any]) -> str:
        """Resolve a stable thread id from AG-UI input payload."""
        thread_id = input_data.get("thread_id") or input_data.get("threadId")
        if thread_id is not None:
            return str(thread_id)
        return str(uuid.uuid4())

    def _resolve_workflow(self, thread_id: str, snapshot_scope: str | None = None) -> Workflow:
        """Get the workflow instance for the current run."""
        if self.workflow is not None:
            return self.workflow

        if self._workflow_factory is None:
            raise NotImplementedError("No workflow is attached. Override run or pass workflow=/workflow_factory=.")

        cache_key = (snapshot_scope, thread_id)
        workflow = self._workflow_by_thread.get(cache_key)
        if workflow is None:
            workflow = self._workflow_factory(thread_id)
            if not isinstance(workflow, Workflow):
                raise TypeError("workflow_factory must return a Workflow instance.")
            self._workflow_by_thread[cache_key] = workflow
        return workflow

    def clear_thread_workflow(self, thread_id: str, snapshot_scope: str | None = None) -> None:
        """Drop cached workflow instances for a thread, optionally limited to one Snapshot Scope."""
        if snapshot_scope is not None:
            self._workflow_by_thread.pop((snapshot_scope, thread_id), None)
            return
        for key in [key for key in self._workflow_by_thread if key[1] == thread_id]:
            del self._workflow_by_thread[key]

    def clear_workflow_cache(self) -> None:
        """Drop all cached thread workflow instances."""
        self._workflow_by_thread.clear()

    async def run(self, input_data: dict[str, Any]) -> AsyncGenerator[BaseEvent]:
        """Run the wrapped workflow and yield AG-UI events.

        Subclasses may override this to provide custom AG-UI streams.

        When ``checkpoint_storage`` is configured on this wrapper, the underlying core
        workflow creates a checkpoint at the end of each superstep, and a run may resume
        from a persisted checkpoint by supplying its id in the AG-UI forwarded props
        (``forwarded_props: {"checkpoint_id": ...}``), which restores the persisted
        workflow state instead of starting a fresh turn.

        Note:
            Checkpointing (the ``agent_framework`` workflow checkpoint mechanism) is
            independent from AG-UI Thread Snapshot persistence (``snapshot_store``).
            The two can be used together, but they persist different things: snapshots
            capture replayable protocol output for a thread, while checkpoints capture
            executor/runtime state for resumable execution.
        """
        mark_feature_used(FeatureIndex.AG_UI)
        thread_id = self._thread_id_from_input(input_data)
        run_id = str(input_data.get("run_id") or input_data.get("runId") or uuid.uuid4())
        snapshot_scope = cast(str | None, input_data.get(_SNAPSHOT_SCOPE_INPUT_KEY))
        raw_messages = list(cast(list[dict[str, Any]], input_data.get("messages", []) or []))
        resume_payload = _extract_resume_payload(input_data)
        snapshot_session = await ThreadSnapshotSession.open(
            store=self.snapshot_store,
            scope=snapshot_scope,
            thread_id=thread_id,
        )
        stored_snapshot = snapshot_session.stored

        checkpoint_storage = self.checkpoint_storage
        checkpoint_id = _checkpoint_id_from_input(input_data)
        if checkpoint_id is not None and checkpoint_storage is None:
            raise ValueError(
                "Resuming from a checkpoint requires checkpoint_storage to be configured on "
                "AgentFrameworkWorkflow (or the AG-UI endpoint)."
            )

        supplied_thread_id = input_data.get("thread_id") or input_data.get("threadId")
        request_owner = (snapshot_scope, str(supplied_thread_id) if supplied_thread_id is not None else None)
        resume_interrupt_ids = {
            str(interrupt["id"])
            for interrupt in _normalize_resume_interrupts(resume_payload)
            if interrupt.get("id") is not None
        }
        workflow = self._resolve_workflow(thread_id, snapshot_scope)
        live_pending_events = await _pending_request_events(self.workflow) if self.workflow is not None else {}
        if self.workflow is not None and checkpoint_id is None:
            for request_event in live_pending_events.values():
                owner = getattr(request_event, _REQUEST_OWNER_ATTRIBUTE, None)
                if owner != request_owner and (owner is not None or request_owner != (None, None)):
                    yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                    yield RunErrorEvent(
                        message="No pending interrupt found for this AG-UI thread.",
                        code="WORKFLOW_RESUME_NOT_FOUND",
                    )
                    return
        if checkpoint_id is not None and checkpoint_storage is not None:
            try:
                checkpoint = await checkpoint_storage.load(checkpoint_id)
            except Exception as exc:
                yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                yield RunErrorEvent(
                    message=f"Could not load workflow checkpoint '{checkpoint_id}': {exc}",
                    code="WORKFLOW_CHECKPOINT_LOAD_FAILED",
                )
                return
            checkpoint_owner = _checkpoint_request_owner(checkpoint.metadata)
            if checkpoint_owner is not None and checkpoint_owner != request_owner:
                yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                yield RunErrorEvent(
                    message=f"No pending interrupt found for checkpointId '{checkpoint_id}'.",
                    code="WORKFLOW_RESUME_NOT_FOUND",
                )
                return
        if self.workflow is not None and checkpoint_id is None:
            for interrupt_id in resume_interrupt_ids:
                request_event = live_pending_events.get(interrupt_id)
                owner = getattr(request_event, _REQUEST_OWNER_ATTRIBUTE, None)
                if owner != request_owner and (owner is not None or request_owner != (None, None)):
                    yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                    yield RunErrorEvent(
                        message=f"No pending interrupt found for resume interruptId '{interrupt_id}'.",
                        code="WORKFLOW_RESUME_NOT_FOUND",
                    )
                    return

        # A checkpoint resume legitimately carries no new messages; it must reach the
        # core workflow's restore path rather than replaying a stored thread snapshot.
        if checkpoint_id is None and snapshot_session.enabled and not raw_messages and resume_payload is None:
            async for event in snapshot_session.hydrate_events(run_id=run_id):
                yield event
            return

        # Seed follow-up turns so the workflow runs with the full persisted thread
        # history instead of just the latest request messages.
        if stored_snapshot is not None and resume_payload is None:
            raw_messages = _reconstruct_messages_from_thread_snapshot(
                stored_messages=stored_snapshot.messages,
                incoming_messages=raw_messages,
                stored_interrupt=stored_snapshot.interrupt,
            )
            input_data["messages"] = raw_messages

        effective_state = snapshot_session.effective_state(
            request_state=input_data.get("state"),
            deferred_defaults=cast(dict[str, Any] | None, input_data.get(_DEFAULT_STATE_INPUT_KEY)),
        )
        if effective_state:
            input_data["state"] = effective_state

        run_checkpoint_storage = checkpoint_storage
        if checkpoint_storage is not None:
            run_checkpoint_storage = _OwnedWorkflowCheckpointStorage(checkpoint_storage, request_owner)
        builder_seed_messages = raw_messages
        if resume_payload is not None or (checkpoint_id is not None and not raw_messages):
            # Resume requests carry only the synthesized interrupt response, and a
            # checkpoint-only resume carries no new messages at all; in both cases seed
            # the builder with stored history to avoid persisting a truncated thread.
            builder_seed_messages = snapshot_session.resume_seeded_messages(builder_seed_messages)
        snapshot_builder = _WorkflowSnapshotBuilder(builder_seed_messages) if snapshot_session.enabled else None
        if snapshot_builder is not None and effective_state:
            # Seed builder state so a run that emits no StateSnapshotEvent still
            # persists the latest known Shared State instead of dropping it.
            state_snapshot = make_json_safe(effective_state)
            if isinstance(state_snapshot, dict):
                snapshot_builder.state = cast(dict[str, Any], state_snapshot)
        run_error_emitted = False
        async for event in run_workflow_stream(
            input_data, workflow, checkpoint_storage=run_checkpoint_storage, checkpoint_id=checkpoint_id
        ):
            if snapshot_builder is not None:
                snapshot_builder.observe(event)
            if (
                self.workflow is not None
                and isinstance(event, ToolCallStartEvent)
                and event.tool_call_name == "request_info"
            ):
                interrupt_id = str(event.tool_call_id)
                pending_event = (await _pending_request_events(workflow)).get(interrupt_id)
                if pending_event is not None and getattr(pending_event, _REQUEST_OWNER_ATTRIBUTE, None) is None:
                    setattr(pending_event, _REQUEST_OWNER_ATTRIBUTE, request_owner)
            if isinstance(event, RunErrorEvent):
                run_error_emitted = True
                if getattr(event, "code", None) == "WORKFLOW_RESUME_CANCELLED":
                    await snapshot_session.clear_interrupts(
                        interrupt_ids=_cancelled_resume_interrupt_ids(resume_payload)
                    )
            yield event

        if snapshot_builder is not None and not run_error_emitted:
            # RUN_FINISHED has already been yielded; the session swallows store
            # failures so they never surface as a second terminal RUN_ERROR event.
            built = snapshot_builder.build()
            await snapshot_session.save(
                messages=built.messages,
                state=built.state,
                interrupt=built.interrupt,
                session_state=built.session_state,
            )
