# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import uuid
from copy import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from ._const import INTERNAL_SOURCE_ID
from ._events import RequestInfoEvent, WorkflowEvent
from ._shared_state import SharedState
from ._typing_utils import is_instance_of

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MessageType(Enum):
    """Enumeration of message types in the workflow."""

    STANDARD = "standard"
    """A standard message between executors."""

    RESPONSE = "response"
    """A response message to a pending request."""


@dataclass
class Message:
    """A class representing a message in the workflow."""

    data: Any
    source_id: str
    target_id: str | None = None
    type: MessageType = MessageType.STANDARD

    # OpenTelemetry trace context fields for message propagation
    # These are plural to support fan-in scenarios where multiple messages are aggregated
    trace_contexts: list[dict[str, str]] | None = None  # W3C Trace Context headers from multiple sources
    source_span_ids: list[str] | None = None  # Publishing span IDs for linking from multiple sources

    # For response messages, the original request data
    original_request_info_event: RequestInfoEvent | None = None

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
        """Convert the Message to a dictionary for serialization."""
        return {
            "data": encode_checkpoint_value(self.data),
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.value,
            "trace_contexts": self.trace_contexts,
            "source_span_ids": self.source_span_ids,
            "original_request_info_event": encode_checkpoint_value(self.original_request_info_event),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Message":
        """Create a Message from a dictionary."""
        # Validation
        if "data" not in data:
            raise KeyError("Missing 'data' field in Message dictionary.")

        if "source_id" not in data:
            raise KeyError("Missing 'source_id' field in Message dictionary.")

        return Message(
            data=decode_checkpoint_value(data["data"]),
            source_id=data["source_id"],
            target_id=data.get("target_id"),
            type=MessageType(data.get("type", "standard")),
            trace_contexts=data.get("trace_contexts"),
            source_span_ids=data.get("source_span_ids"),
            original_request_info_event=decode_checkpoint_value(data.get("original_request_info_event")),
        )


class _WorkflowState(TypedDict):
    """TypedDict representing the serializable state of a workflow execution.

    This includes all state data needed for checkpointing and restoration.
    """

    messages: dict[str, list[dict[str, Any]]]
    shared_state: dict[str, Any]
    iteration_count: int
    pending_request_info_events: dict[str, dict[str, Any]]


@runtime_checkable
class RunnerContext(Protocol):
    """Protocol for the execution context used by the runner.

    A single context that supports messaging, events, and optional checkpointing.
    If checkpoint storage is not configured, checkpoint methods may raise.
    """

    async def send_message(self, message: Message) -> None:
        """Send a message from the executor to the context.

        Args:
            message: The message to be sent.
        """
        ...

    async def drain_messages(self) -> dict[str, list[Message]]:
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

    # Checkpointing APIs (optional, enabled by storage)
    def set_workflow_id(self, workflow_id: str) -> None:
        """Set the workflow ID for the context."""
        ...

    def reset_for_new_run(self) -> None:
        """Reset the context for a new workflow run."""
        ...

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (run_stream), False for non-streaming (run).
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
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a checkpoint of the current workflow state.

        Args:
            shared_state: The shared state to include in the checkpoint.
                          This is needed to capture the full state of the workflow.
                          The shared state is not managed by the context itself.
            iteration_count: The current iteration count of the workflow.
            metadata: Optional metadata to associate with the checkpoint.

        Returns:
            The ID of the created checkpoint.
        """
        ...

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
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

    async def add_request_info_event(self, event: RequestInfoEvent) -> None:
        """Add a RequestInfoEvent to the context and track it for correlation.

        Args:
            event: The RequestInfoEvent to be added.
        """
        ...

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        """Send a response correlated to a pending request.

        Args:
            request_id: The ID of the original request.
            response: The response data to be sent.
        """
        ...

    async def get_pending_request_info_events(self) -> dict[str, RequestInfoEvent]:
        """Get the mapping of request IDs to their corresponding RequestInfoEvent.

        Returns:
            A dictionary mapping request IDs to their corresponding RequestInfoEvent.
        """
        ...


class InProcRunnerContext:
    """In-process execution context for local execution and optional checkpointing."""

    def __init__(self, checkpoint_storage: CheckpointStorage | None = None):
        """Initialize the in-process execution context.

        Args:
            checkpoint_storage: Optional storage to enable checkpointing.
        """
        self._messages: dict[str, list[Message]] = {}
        # Event queue for immediate streaming of events (e.g., AgentRunUpdateEvent)
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

        # An additional storage for pending request info events
        self._pending_request_info_events: dict[str, RequestInfoEvent] = {}

        # Checkpointing configuration/state
        self._checkpoint_storage = checkpoint_storage
        self._runtime_checkpoint_storage: CheckpointStorage | None = None
        self._workflow_id: str | None = None

        # Streaming flag - set by workflow's run_stream() vs run()
        self._streaming: bool = False

    # region Messaging and Events
    async def send_message(self, message: Message) -> None:
        self._messages.setdefault(message.source_id, [])
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
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
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        storage = self._get_effective_checkpoint_storage()
        if not storage:
            raise ValueError("Checkpoint storage not configured")

        self._workflow_id = self._workflow_id or str(uuid.uuid4())
        state = await self._get_serialized_workflow_state(shared_state, iteration_count)

        checkpoint = WorkflowCheckpoint(
            workflow_id=self._workflow_id,
            messages=state["messages"],
            shared_state=state["shared_state"],
            pending_request_info_events=state["pending_request_info_events"],
            iteration_count=state["iteration_count"],
            metadata=metadata or {},
        )
        checkpoint_id = await storage.save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {checkpoint_id} for workflow {self._workflow_id}")
        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        storage = self._get_effective_checkpoint_storage()
        if not storage:
            raise ValueError("Checkpoint storage not configured")
        return await storage.load_checkpoint(checkpoint_id)

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
            self._messages[source_id] = [Message.from_dict(msg) for msg in message_list]

        # Restore pending request info events
        self._pending_request_info_events.clear()
        pending_requests_data = checkpoint.pending_request_info_events
        for request_id, request_data in pending_requests_data.items():
            request_info_event = RequestInfoEvent.from_dict(request_data)
            self._pending_request_info_events[request_id] = request_info_event
            await self.add_event(request_info_event)

        # Restore workflow ID
        self._workflow_id = checkpoint.workflow_id

    # endregion Checkpointing

    def set_workflow_id(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (run_stream), False for non-streaming (run).
        """
        self._streaming = streaming

    def is_streaming(self) -> bool:
        """Check if the workflow is in streaming mode.

        Returns:
            True if streaming mode is enabled, False otherwise.
        """
        return self._streaming

    async def _get_serialized_workflow_state(self, shared_state: SharedState, iteration_count: int) -> _WorkflowState:
        serialized_messages: dict[str, list[dict[str, Any]]] = {}
        for source_id, message_list in self._messages.items():
            serialized_messages[source_id] = [msg.to_dict() for msg in message_list]

        serialized_pending_request_info_events: dict[str, dict[str, Any]] = {
            request_id: request.to_dict() for request_id, request in self._pending_request_info_events.items()
        }

        return {
            "messages": serialized_messages,
            "shared_state": encode_checkpoint_value(await shared_state.export_state()),
            "iteration_count": iteration_count,
            "pending_request_info_events": serialized_pending_request_info_events,
        }

    async def add_request_info_event(self, event: RequestInfoEvent) -> None:
        """Add a RequestInfoEvent to the context and track it for correlation.

        Args:
            event: The RequestInfoEvent to be added.
        """
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

        # Validate response type if specified
        if event.response_type and not is_instance_of(response, event.response_type):
            raise TypeError(
                f"Response type mismatch for request_id {request_id}: "
                f"expected {event.response_type.__name__}, got {type(response).__name__}"
            )

        # Create ResponseMessage instance
        response_msg = Message(
            data=response,
            source_id=INTERNAL_SOURCE_ID(event.source_executor_id),
            target_id=event.source_executor_id,
            type=MessageType.RESPONSE,
            original_request_info_event=event,
        )

        await self.send_message(response_msg)

    async def get_pending_request_info_events(self) -> dict[str, RequestInfoEvent]:
        """Get the mapping of request IDs to their corresponding RequestInfoEvent.

        Returns:
            A dictionary mapping request IDs to their corresponding RequestInfoEvent.
        """
        return dict(self._pending_request_info_events)
