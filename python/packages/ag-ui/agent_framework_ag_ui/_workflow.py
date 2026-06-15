# Copyright (c) Microsoft. All rights reserved.

"""Workflow wrapper for AG-UI protocol compatibility."""

from __future__ import annotations

import copy
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
from agent_framework import Workflow

from ._message_adapters import agui_messages_to_snapshot_format
from ._run_common import (
    _build_run_finished_event,
    _extract_resume_payload,
    _reconstruct_messages_from_thread_snapshot,
)
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshot,
    AGUIThreadSnapshotStore,
)
from ._utils import generate_event_id, make_json_safe
from ._workflow_run import run_workflow_stream

logger = logging.getLogger(__name__)

WorkflowFactory = Callable[[str], Workflow]


def _event_messages_to_snapshot_dicts(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert AG-UI message event models to plain snapshot dictionaries."""
    safe_messages = make_json_safe(messages)
    if not isinstance(safe_messages, list):
        return []
    return [cast(dict[str, Any], message) for message in safe_messages if isinstance(message, dict)]


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
            interrupt = make_json_safe(getattr(event, "interrupt", None))
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


async def _hydrate_workflow_thread_snapshot(
    *,
    snapshot_store: AGUIThreadSnapshotStore,
    scope: str,
    thread_id: str,
    run_id: str,
) -> AsyncGenerator[BaseEvent]:
    """Replay the latest stored workflow AG-UI Thread Snapshot without invoking the workflow."""
    yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
    snapshot = await snapshot_store.get(scope=scope, thread_id=thread_id)
    if snapshot is None:
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    if snapshot.state is not None:
        yield StateSnapshotEvent(snapshot=snapshot.state)
    if snapshot.messages:
        yield MessagesSnapshotEvent(messages=snapshot.messages)  # type: ignore[arg-type]
    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=snapshot.interrupt)


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
    ) -> None:
        """Initialize the AG-UI workflow wrapper.

        Args:
            workflow: Optional workflow instance to expose.
            workflow_factory: Optional factory for thread-scoped workflow instances.
            name: Optional workflow name.
            description: Optional workflow description.
            snapshot_store: Optional AG-UI Thread Snapshot store. Snapshot persistence remains inactive unless
                endpoint setup also provides an explicit Snapshot Scope resolver.
        """
        if workflow is not None and workflow_factory is not None:
            raise ValueError("Pass either workflow= or workflow_factory=, not both.")

        self.workflow = workflow
        self._workflow_factory = workflow_factory
        # Cache keyed by (snapshot_scope, thread_id): the Snapshot Scope is the
        # authorization boundary, so the same thread id under different scopes
        # must never share an in-memory workflow instance.
        self._workflow_by_thread: dict[tuple[str | None, str], Workflow] = {}
        self.name = name if name is not None else getattr(workflow, "name", "workflow")
        self.description = description if description is not None else getattr(workflow, "description", "")
        self.snapshot_store = snapshot_store

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
        """
        thread_id = self._thread_id_from_input(input_data)
        run_id = str(input_data.get("run_id") or input_data.get("runId") or uuid.uuid4())
        snapshot_scope = cast(str | None, input_data.get(_SNAPSHOT_SCOPE_INPUT_KEY))
        raw_messages = list(cast(list[dict[str, Any]], input_data.get("messages", []) or []))
        resume_payload = _extract_resume_payload(input_data)
        snapshot_store = self.snapshot_store

        if snapshot_store is not None and snapshot_scope is not None and not raw_messages and resume_payload is None:
            async for event in _hydrate_workflow_thread_snapshot(
                snapshot_store=snapshot_store,
                scope=snapshot_scope,
                thread_id=thread_id,
                run_id=run_id,
            ):
                yield event
            return

        # Load the stored snapshot for follow-up turns so the workflow runs with the
        # full persisted thread history instead of just the latest request messages.
        stored_snapshot: AGUIThreadSnapshot | None = None
        if snapshot_store is not None and snapshot_scope is not None:
            stored_snapshot = await snapshot_store.get(scope=snapshot_scope, thread_id=thread_id)
            if stored_snapshot is not None and resume_payload is None:
                raw_messages = _reconstruct_messages_from_thread_snapshot(
                    stored_messages=stored_snapshot.messages,
                    incoming_messages=raw_messages,
                    stored_interrupt=stored_snapshot.interrupt,
                )
                input_data["messages"] = raw_messages

        # Merge stored state with request overrides, then fill endpoint-deferred
        # defaults only for keys missing from both.
        request_state = input_data.get("state")
        deferred_default_state = cast(dict[str, Any] | None, input_data.get(_DEFAULT_STATE_INPUT_KEY))
        effective_state: dict[str, Any] = {}
        if stored_snapshot is not None and stored_snapshot.state is not None:
            effective_state.update(stored_snapshot.state)
        if isinstance(request_state, dict):
            effective_state.update(cast(dict[str, Any], request_state))
        if deferred_default_state:
            for key, value in deferred_default_state.items():
                if key not in effective_state:
                    effective_state[key] = copy.deepcopy(value)
        if effective_state:
            input_data["state"] = effective_state

        workflow = self._resolve_workflow(thread_id, snapshot_scope)
        builder_seed_messages = raw_messages
        if resume_payload is not None and stored_snapshot is not None:
            # Resume requests carry only the synthesized interrupt response, so seed
            # the builder with stored history to avoid persisting a truncated thread.
            builder_seed_messages = [
                copy.deepcopy(message) for message in stored_snapshot.messages
            ] + builder_seed_messages
        snapshot_builder = (
            _WorkflowSnapshotBuilder(builder_seed_messages)
            if snapshot_store is not None and snapshot_scope is not None
            else None
        )
        if snapshot_builder is not None and effective_state:
            # Seed builder state so a run that emits no StateSnapshotEvent still
            # persists the latest known Shared State instead of dropping it.
            state_snapshot = make_json_safe(effective_state)
            if isinstance(state_snapshot, dict):
                snapshot_builder.state = cast(dict[str, Any], state_snapshot)
        run_error_emitted = False
        async for event in run_workflow_stream(input_data, workflow):
            if snapshot_builder is not None:
                snapshot_builder.observe(event)
            if isinstance(event, RunErrorEvent):
                run_error_emitted = True
            yield event

        if (
            snapshot_builder is not None
            and not run_error_emitted
            and snapshot_store is not None
            and snapshot_scope is not None
        ):
            try:
                await snapshot_store.save(
                    scope=snapshot_scope,
                    thread_id=thread_id,
                    snapshot=snapshot_builder.build(),
                )
            except Exception:
                # RUN_FINISHED has already been yielded; a store failure must not
                # surface as a second terminal RUN_ERROR event. The previous
                # snapshot stays available for hydration.
                logger.exception(
                    "Failed to save AG-UI Thread Snapshot for scope=%s thread_id=%s; keeping previous snapshot.",
                    snapshot_scope,
                    thread_id,
                )
