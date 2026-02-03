# Copyright (c) Microsoft. All rights reserved.

"""Runner context for Azure Functions activity execution.

This module provides the CapturingRunnerContext class that captures messages
and events produced during executor execution within Azure Functions activities.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_framework import (
    CheckpointStorage,
    Message,
    RequestInfoEvent,
    RunnerContext,
    SharedState,
    WorkflowCheckpoint,
    WorkflowEvent,
)


class CapturingRunnerContext(RunnerContext):
    """A RunnerContext implementation that captures messages and events for Azure Functions activities.

    This context is designed for executing standard Executors within Azure Functions activities.
    It captures all messages and events produced during execution without requiring durable
    entity storage, allowing the results to be returned to the orchestrator.

    Unlike the full InProcRunnerContext, this implementation:
    - Does NOT support checkpointing (always returns False for has_checkpointing)
    - Does NOT support streaming (always returns False for is_streaming)
    - Captures messages and events in memory for later retrieval

    The orchestrator manages state coordination; this context just captures execution output.
    """

    def __init__(self) -> None:
        """Initialize the capturing runner context."""
        self._messages: dict[str, list[Message]] = {}
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()
        self._pending_request_info_events: dict[str, RequestInfoEvent] = {}
        self._workflow_id: str | None = None
        self._streaming: bool = False

    # region Messaging

    async def send_message(self, message: Message) -> None:
        """Capture a message sent by an executor."""
        self._messages.setdefault(message.source_id, [])
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
        """Drain and return all captured messages."""
        from copy import copy

        messages = copy(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        """Check if there are any captured messages."""
        return bool(self._messages)

    # endregion Messaging

    # region Events

    async def add_event(self, event: WorkflowEvent) -> None:
        """Capture an event produced during execution."""
        await self._event_queue.put(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all currently queued events without blocking."""
        events: list[WorkflowEvent] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    async def has_events(self) -> bool:
        """Check if there are any queued events."""
        return not self._event_queue.empty()

    async def next_event(self) -> WorkflowEvent:
        """Wait for and return the next event."""
        return await self._event_queue.get()

    # endregion Events

    # region Checkpointing (not supported in activity context)

    def has_checkpointing(self) -> bool:
        """Checkpointing is not supported in activity context."""
        return False

    def set_runtime_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        """No-op: checkpointing not supported in activity context."""
        pass

    def clear_runtime_checkpoint_storage(self) -> None:
        """No-op: checkpointing not supported in activity context."""
        pass

    async def create_checkpoint(
        self,
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    # endregion Checkpointing

    # region Workflow Configuration

    def set_workflow_id(self, workflow_id: str) -> None:
        """Set the workflow ID."""
        self._workflow_id = workflow_id

    def reset_for_new_run(self) -> None:
        """Reset the context for a new run."""
        self._messages.clear()
        self._event_queue = asyncio.Queue()
        self._pending_request_info_events.clear()
        self._streaming = False

    def set_streaming(self, streaming: bool) -> None:
        """Set streaming mode (not used in activity context)."""
        self._streaming = streaming

    def is_streaming(self) -> bool:
        """Check if streaming mode is enabled (always False in activity context)."""
        return self._streaming

    # endregion Workflow Configuration

    # region Request Info Events

    async def add_request_info_event(self, event: RequestInfoEvent) -> None:
        """Add a RequestInfoEvent and track it for correlation."""
        self._pending_request_info_events[event.request_id] = event
        await self.add_event(event)

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        """Send a response correlated to a pending request.

        Note: This is not supported in activity context since human-in-the-loop
        scenarios require orchestrator-level coordination.
        """
        raise NotImplementedError(
            "send_request_info_response is not supported in Azure Functions activity context. "
            "Human-in-the-loop scenarios should be handled at the orchestrator level."
        )

    async def get_pending_request_info_events(self) -> dict[str, RequestInfoEvent]:
        """Get the mapping of request IDs to their corresponding RequestInfoEvent."""
        return dict(self._pending_request_info_events)

    # endregion Request Info Events
