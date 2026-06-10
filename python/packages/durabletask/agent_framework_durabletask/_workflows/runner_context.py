# Copyright (c) Microsoft. All rights reserved.

"""Runner context for activity execution within durable orchestrations.

This module provides the :class:`CapturingRunnerContext` class that captures
messages and events produced during executor execution within activities.
It is host-agnostic and works on any durable task host.
"""

from __future__ import annotations

import asyncio
from copy import copy
from typing import Any

from agent_framework import (
    CheckpointStorage,
    RunnerContext,
    WorkflowCheckpoint,
    WorkflowEvent,
    WorkflowMessage,
)
from agent_framework._workflows._runner_context import YieldOutputClassifier, YieldOutputEventType
from agent_framework._workflows._state import State


class CapturingRunnerContext(RunnerContext):
    """A RunnerContext that captures messages and events for durable activities.

    This context captures all messages and events produced during execution
    without requiring durable entity storage, allowing the results to be
    returned to the orchestrator.

    Checkpointing is not supported — the orchestrator manages state.
    """

    def __init__(self) -> None:
        self._messages: dict[str, list[WorkflowMessage]] = {}
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()
        self._pending_request_info_events: dict[str, WorkflowEvent[Any]] = {}
        self._workflow_id: str | None = None
        self._streaming: bool = False
        self._yield_output_classifier: YieldOutputClassifier = lambda _executor_id: "output"

    # -- Messaging ------------------------------------------------------------

    async def send_message(self, message: WorkflowMessage) -> None:
        self._messages.setdefault(message.source_id, [])
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[WorkflowMessage]]:
        messages = copy(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        return bool(self._messages)

    # -- Events ---------------------------------------------------------------

    async def add_event(self, event: WorkflowEvent) -> None:
        await self._event_queue.put(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        events: list[WorkflowEvent] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    async def has_events(self) -> bool:
        return not self._event_queue.empty()

    async def next_event(self) -> WorkflowEvent:
        return await self._event_queue.get()

    # -- Checkpointing (not supported) ----------------------------------------

    def has_checkpointing(self) -> bool:
        return False

    def set_runtime_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        pass

    def clear_runtime_checkpoint_storage(self) -> None:
        pass

    async def create_checkpoint(
        self,
        workflow_name: str,
        graph_signature_hash: str,
        state: State,
        previous_checkpoint_id: str | None,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError("Checkpointing is not supported in activity context")

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        raise NotImplementedError("Checkpointing is not supported in activity context")

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        raise NotImplementedError("Checkpointing is not supported in activity context")

    # -- Workflow configuration -----------------------------------------------

    def set_workflow_id(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id

    def reset_for_new_run(self) -> None:
        self._messages.clear()
        self._event_queue = asyncio.Queue()
        self._pending_request_info_events.clear()
        self._streaming = False

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming

    def is_streaming(self) -> bool:
        return self._streaming

    # -- Yield-output classification -------------------------------------------

    def set_yield_output_classifier(self, classifier: YieldOutputClassifier) -> None:
        """Set the classifier used by ``WorkflowContext.yield_output()``."""
        self._yield_output_classifier = classifier

    def classify_yielded_output(self, executor_id: str) -> YieldOutputEventType | None:
        """Classify an executor's yield_output payload as output, intermediate, or hidden."""
        return self._yield_output_classifier(executor_id)

    # -- Request Info Events --------------------------------------------------

    async def add_request_info_event(self, event: WorkflowEvent[Any]) -> None:
        self._pending_request_info_events[event.request_id] = event
        await self.add_event(event)

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        raise NotImplementedError(
            "send_request_info_response is not supported in activity context. "
            "Human-in-the-loop scenarios should be handled at the orchestrator level."
        )

    async def get_pending_request_info_events(self) -> dict[str, WorkflowEvent[Any]]:
        return dict(self._pending_request_info_events)
