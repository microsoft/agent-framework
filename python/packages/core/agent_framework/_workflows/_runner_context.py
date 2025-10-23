# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import uuid
from copy import copy
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, TypeVar, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from ._events import WorkflowEvent
from ._shared_state import SharedState

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Message:
    """A class representing a message in the workflow."""

    data: Any
    source_id: str
    target_id: str | None = None

    # OpenTelemetry trace context fields for message propagation
    # These are plural to support fan-in scenarios where multiple messages are aggregated
    trace_contexts: list[dict[str, str]] | None = None  # W3C Trace Context headers from multiple sources
    source_span_ids: list[str] | None = None  # Publishing span IDs for linking from multiple sources

    # Backward compatibility properties
    @property
    def trace_context(self) -> dict[str, str] | None:
        """Get the first trace context for backward compatibility."""
        return self.trace_contexts[0] if self.trace_contexts else None

    @property
    def source_span_id(self) -> str | None:
        """Get the first source span ID for backward compatibility."""
        return self.source_span_ids[0] if self.source_span_ids else None


class _WorkflowState(TypedDict):
    """TypedDict representing the serializable state of a workflow execution.

    This includes all state data needed for checkpointing and restoration.
    """

    messages: dict[str, list[dict[str, Any]]]
    shared_state: dict[str, Any]
    iteration_count: int


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

        # Checkpointing configuration/state
        self._checkpoint_storage = checkpoint_storage
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

    def has_checkpointing(self) -> bool:
        return self._checkpoint_storage is not None

    async def create_checkpoint(
        self,
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        self._workflow_id = self._workflow_id or str(uuid.uuid4())
        state = await self._get_serialized_workflow_state(shared_state, iteration_count)

        checkpoint = WorkflowCheckpoint(
            workflow_id=self._workflow_id,
            messages=state["messages"],
            shared_state=state["shared_state"],
            iteration_count=state["iteration_count"],
            metadata=metadata or {},
        )
        checkpoint_id = await self._checkpoint_storage.save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {checkpoint_id} for workflow {self._workflow_id}")
        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")
        return await self._checkpoint_storage.load_checkpoint(checkpoint_id)

    def reset_for_new_run(self) -> None:
        """Reset the context for a new workflow run.

        This clears messages, events, and resets streaming flag.
        """
        self._messages.clear()
        # Clear any pending events (best-effort) by recreating the queue
        self._event_queue = asyncio.Queue()
        self._streaming = False  # Reset streaming flag

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        self._messages.clear()
        messages_data = checkpoint.messages
        for source_id, message_list in messages_data.items():
            self._messages[source_id] = [
                Message(
                    data=decode_checkpoint_value(msg.get("data")),
                    source_id=msg.get("source_id", ""),
                    target_id=msg.get("target_id"),
                    trace_contexts=msg.get("trace_contexts"),
                    source_span_ids=msg.get("source_span_ids"),
                )
                for msg in message_list
            ]

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
        serializable_messages: dict[str, list[dict[str, Any]]] = {}
        for source_id, message_list in self._messages.items():
            serializable_messages[source_id] = [
                {
                    "data": encode_checkpoint_value(msg.data),
                    "source_id": msg.source_id,
                    "target_id": msg.target_id,
                    "trace_contexts": msg.trace_contexts,
                    "source_span_ids": msg.source_span_ids,
                }
                for msg in message_list
            ]

        return {
            "messages": serializable_messages,
            "shared_state": encode_checkpoint_value(await shared_state.export_state()),
            "iteration_count": iteration_count,
        }
