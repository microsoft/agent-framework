# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
from copy import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar, runtime_checkable

from ._checkpoint import CheckpointID, CheckpointStorage, WorkflowCheckpoint
from ._const import INTERNAL_SOURCE_ID
from ._events import WorkflowEvent
from ._state import State
from ._typing_utils import is_instance_of

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MessageType(Enum):
    """Enumeration of WorkflowMessage types in the workflow."""

    STANDARD = "standard"
    """A standard WorkflowMessage between executors."""

    RESPONSE = "response"
    """A response WorkflowMessage to a pending request."""


@dataclass
class WorkflowMessage:
    """A class representing a WorkflowMessage in the workflow."""

    data: Any
    source_id: str
    target_id: str | None = None
    type: MessageType = MessageType.STANDARD

    # OpenTelemetry trace context fields for WorkflowMessage propagation
    # These are plural to support fan-in scenarios where multiple messages are aggregated
    trace_contexts: list[dict[str, str]] | None = None  # W3C Trace Context headers from multiple sources
    source_span_ids: list[str] | None = None  # Publishing span IDs for linking from multiple sources

    # For response messages, the original request data
    original_request_info_event: WorkflowEvent[Any] | None = None

    # Backward compatibility properties
    @property
    def trace_context(self) -> dict[str, str] | None:
        """Get the first trace context for backward compatibility."""
        return self.trace_contexts[0] if self.trace_contexts else None

    @property
    def source_span_id(self) -> str | None:
        """Get the first source span ID for backward compatibility."""
        return self.source_span_ids[0] if self.source_span_ids else None

    def to_dict(self) -> dict[str, Any]:
        """Convert the WorkflowMessage to a dictionary for serialization."""
        return {
            "data": self.data,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.value,
            "trace_contexts": self.trace_contexts,
            "source_span_ids": self.source_span_ids,
            "original_request_info_event": self.original_request_info_event,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> WorkflowMessage:
        """Create a WorkflowMessage from a dictionary."""
        # Validation
        if "data" not in data:
            raise KeyError("Missing 'data' field in WorkflowMessage dictionary.")

        if "source_id" not in data:
            raise KeyError("Missing 'source_id' field in WorkflowMessage dictionary.")

        return WorkflowMessage(
            data=data["data"],
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            type=MessageType(data.get("type", "standard")),
            trace_contexts=data.get("trace_contexts"),
            source_span_ids=data.get("source_span_ids"),
            original_request_info_event=data.get("original_request_info_event"),
        )


@runtime_checkable
class RunnerContext(Protocol):
    """Protocol for the execution context used by the runner.

    A single context that supports messaging, events, and optional checkpointing.
    If checkpoint storage is not configured, checkpoint methods may raise.
    """

    async def send_message(self, WorkflowMessage: WorkflowMessage) -> None:
        """Send a WorkflowMessage from the executor to the context.

        Args:
            WorkflowMessage: The WorkflowMessage to be sent.
        """
        ...

    async def drain_messages(self) -> dict[str, list[WorkflowMessage]]:
        """Drain all messages from the context.

        Returns:
            A dictionary mapping executor IDs to lists of messages.
        """
        ...

    async def has_messages(self) -> bool:
        """Check if there are any messages in the context.

        Returns:
            True if there are messages, False otherwise.
        """
        ...

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the execution context.

        Args:
            event: The event to be added.
        """
        ...

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all events from the context.

        Returns:
            A list of events that were added to the context.
        """
        ...

    async def has_events(self) -> bool:
        """Check if there are any events in the context.

        Returns:
            True if there are events, False otherwise.
        """
        ...

    async def next_event(self) -> WorkflowEvent:  # pragma: no cover - interface only
        """Wait for and return the next event emitted by the workflow run."""
        ...

    # Checkpointing capability
    def has_checkpointing(self) -> bool:
        """Check if the context supports checkpointing.

        Returns:
            True if checkpointing is supported, False otherwise.
        """
        ...

    def set_runtime_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        """Set runtime checkpoint storage to override build-time configuration.

        Args:
            storage: The checkpoint storage to use for this run.
        """
        ...

    def clear_runtime_checkpoint_storage(self) -> None:
        """Clear runtime checkpoint storage override."""
        ...

    def reset_for_new_run(self) -> None:
        """Reset the context for a new workflow run."""
        ...

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (stream=True), False for non-streaming (stream=False).
        """
        ...

    def is_streaming(self) -> bool:
        """Check if the workflow is in streaming mode.

        Returns:
            True if streaming mode is enabled, False otherwise.
        """
        ...

    async def create_checkpoint(
        self,
        workflow_name: str,
        graph_signature_hash: str,
        state: State,
        previous_checkpoint_id: CheckpointID | None,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointID:
        """Create a checkpoint of the current workflow state.

        Args:
            workflow_name: The name of the workflow for which the checkpoint is being created.
            graph_signature_hash: Hash of the workflow graph topology to
                validate checkpoint compatibility during restore.
            state: The state to include in the checkpoint.
                   This is needed to capture the full state of the workflow.
                   The state is not managed by the context itself.
            previous_checkpoint_id: The ID of the previous checkpoint, if any, to form a checkpoint chain.
            iteration_count: The current iteration count of the workflow.
            metadata: Optional metadata to associate with the checkpoint.

        Returns:
            The ID of the created checkpoint.
        """
        ...

    async def load_checkpoint(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint | None:
        """Load a checkpoint without mutating the current context state.

        Args:
            checkpoint_id: The ID of the checkpoint to load.

        Returns:
            The loaded checkpoint, or None if it does not exist.
        """
        ...

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Apply a checkpoint to the current context, mutating its state.

        Args:
            checkpoint: The checkpoint whose state is to be applied.
        """
        ...

    async def add_request_info_event(self, event: WorkflowEvent[Any]) -> None:
        """Add a request_info event to the context and track it for correlation.

        Args:
            event: The WorkflowEvent with type='request_info' to be added.
        """
        ...

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        """Send a response correlated to a pending request.

        Args:
            request_id: The ID of the original request.
            response: The response data to be sent.
        """
        ...

    async def get_pending_request_info_events(self) -> dict[str, WorkflowEvent[Any]]:
        """Get the mapping of request IDs to their corresponding request_info events.

        Returns:
            A dictionary mapping request IDs to their corresponding WorkflowEvent (type='request_info').
        """
        ...


class InProcRunnerContext:
    """In-process execution context for local execution and optional checkpointing."""

    def __init__(self, checkpoint_storage: CheckpointStorage | None = None):
        """Initialize the in-process execution context.

        Args:
            checkpoint_storage: Optional storage to enable checkpointing.
        """
        self._messages: dict[str, list[WorkflowMessage]] = {}
        # Event queue for immediate streaming of events
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

        # An additional storage for pending request info events
        self._pending_request_info_events: dict[str, WorkflowEvent[Any]] = {}

        # Checkpointing configuration/state
        self._checkpoint_storage = checkpoint_storage
        self._runtime_checkpoint_storage: CheckpointStorage | None = None

        # Streaming flag - set by workflow's run(..., stream=True) vs run(..., stream=False)
        self._streaming: bool = False

    # region Messaging and Events
    async def send_message(self, WorkflowMessage: WorkflowMessage) -> None:
        self._messages.setdefault(WorkflowMessage.source_id, [])
        self._messages[WorkflowMessage.source_id].append(WorkflowMessage)

    async def drain_messages(self) -> dict[str, list[WorkflowMessage]]:
        messages = copy(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        return bool(self._messages)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the context immediately.

        Events are enqueued so runners can stream them in real time instead of
        waiting for superstep boundaries.
        """
        await self._event_queue.put(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all currently queued events without blocking for new ones."""
        events: list[WorkflowEvent] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:  # type: ignore[attr-defined]
                break
        return events

    async def has_events(self) -> bool:
        return not self._event_queue.empty()

    async def next_event(self) -> WorkflowEvent:
        """Wait for and return the next event.

        Used by the runner to interleave event emission with ongoing iteration work.
        """
        return await self._event_queue.get()

    # endregion Messaging and Events

    # region Checkpointing

    def _get_effective_checkpoint_storage(self) -> CheckpointStorage | None:
        """Get the effective checkpoint storage (runtime override or build-time)."""
        return self._runtime_checkpoint_storage or self._checkpoint_storage

    def set_runtime_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        """Set runtime checkpoint storage to override build-time configuration.

        Args:
            storage: The checkpoint storage to use for this run.
        """
        self._runtime_checkpoint_storage = storage

    def clear_runtime_checkpoint_storage(self) -> None:
        """Clear runtime checkpoint storage override.

        This is called automatically by workflow execution methods after a run completes,
        ensuring runtime storage doesn't leak across runs.
        """
        self._runtime_checkpoint_storage = None

    def has_checkpointing(self) -> bool:
        return self._get_effective_checkpoint_storage() is not None

    async def create_checkpoint(
        self,
        workflow_name: str,
        graph_signature_hash: str,
        state: State,
        previous_checkpoint_id: CheckpointID | None,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointID:
        storage = self._get_effective_checkpoint_storage()
        if not storage:
            raise ValueError("Checkpoint storage not configured")

        checkpoint = WorkflowCheckpoint(
            workflow_name=workflow_name,
            graph_signature_hash=graph_signature_hash,
            previous_checkpoint_id=previous_checkpoint_id,
            messages=dict(self._messages),
            state=state.export_state(),
            pending_request_info_events=dict(self._pending_request_info_events),
            iteration_count=iteration_count,
            metadata=metadata or {},
        )
        checkpoint_id = await storage.save(checkpoint)
        logger.debug(f"Created checkpoint {checkpoint_id}")
        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        storage = self._get_effective_checkpoint_storage()
        if not storage:
            raise ValueError("Checkpoint storage not configured")
        return await storage.load(checkpoint_id)

    def reset_for_new_run(self) -> None:
        """Reset the context for a new workflow run.

        This clears messages, events, and resets streaming flag.
        Runtime checkpoint storage is NOT cleared here as it's managed at the workflow level.
        """
        self._messages.clear()
        # Clear any pending events (best-effort) by recreating the queue
        self._event_queue = asyncio.Queue()
        self._streaming = False  # Reset streaming flag

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Apply a checkpoint to the current context, mutating its state."""
        # Restore messages
        self._messages.clear()
        messages_data = checkpoint.messages
        for source_id, message_list in messages_data.items():
            self._messages[source_id] = list(message_list)

        # Restore pending request info events
        self._pending_request_info_events.clear()
        for request_id, request_info_event in checkpoint.pending_request_info_events.items():
            self._pending_request_info_events[request_id] = request_info_event
            await self.add_event(request_info_event)

    # endregion Checkpointing

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (run(stream=True)), False for non-streaming.
        """
        self._streaming = streaming

    def is_streaming(self) -> bool:
        """Check if the workflow is in streaming mode.

        Returns:
            True if streaming mode is enabled, False otherwise.
        """
        return self._streaming

    async def add_request_info_event(self, event: WorkflowEvent[Any]) -> None:
        """Add a request_info event to the context and track it for correlation.

        Args:
            event: The WorkflowEvent with type='request_info' to be added.
        """
        if event.type != "request_info":
            raise ValueError("Event type must be 'request_info'")
        self._pending_request_info_events[event.request_id] = event
        await self.add_event(event)

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        """Send a response correlated to a pending request.

        Args:
            request_id: The ID of the original request.
            response: The response data to be sent.
        """
        event = self._pending_request_info_events.pop(request_id, None)
        if not event:
            raise ValueError(f"No pending request found for request_id: {request_id}")

        try:
            # Validate response type if specified
            if event.response_type and not is_instance_of(response, event.response_type):
                expected_type_name = getattr(event.response_type, "__name__", str(event.response_type))
                raise TypeError(
                    f"Response type mismatch for request_id {request_id}: "
                    f"expected {expected_type_name}, got {type(response).__name__}"
                )

            source_executor_id = event.source_executor_id

            # Create ResponseMessage instance
            response_msg = WorkflowMessage(
                data=response,
                source_id=INTERNAL_SOURCE_ID(source_executor_id),
                target_id=source_executor_id,
                type=MessageType.RESPONSE,
                original_request_info_event=event,
            )

            await self.send_message(response_msg)
        except BaseException:
            # Restore pending request so callers can retry (for example, type mismatch
            # from an async request handler or cancellation while submitting).
            self._pending_request_info_events[request_id] = event
            raise

    async def get_pending_request_info_events(self) -> dict[str, WorkflowEvent[Any]]:
        """Get the mapping of request IDs to their corresponding request_info events.

        Returns:
            A dictionary mapping request IDs to their corresponding WorkflowEvent (type='request_info').
        """
        return dict(self._pending_request_info_events)
