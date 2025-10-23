# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import uuid
from copy import copy
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, TypeVar, cast, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from ._const import DEFAULT_MAX_ITERATIONS
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


class WorkflowState(TypedDict):
    """TypedDict representing the serializable state of a workflow execution.

    This includes all state data needed for checkpointing and restoration.
    """

    messages: dict[str, list[dict[str, Any]]]
    shared_state: dict[str, Any]
    executor_states: dict[str, dict[str, Any]]
    iteration_count: int
    max_iterations: int


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

    async def set_executor_state(self, executor_id: str, state: dict[str, Any]) -> None:
        """Set the state for a specific executor.

        Args:
            executor_id: The ID of the executor whose state is being set.
            state: The state data to be set for the executor.
        """
        ...

    async def get_executor_state(self, executor_id: str) -> dict[str, Any] | None:
        """Get the state for a specific executor.

        Args:
            executor_id: The ID of the executor whose state is being retrieved.

        Returns:
            The state data for the executor, or None if not found.
        """
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

    def reset_for_new_run(self, workflow_shared_state: SharedState | None = None) -> None:
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

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        """Create a checkpoint of the current workflow state.

        Args:
            metadata: Optional metadata to associate with the checkpoint.
        """
        ...

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint without mutating the current context state."""
        ...

    async def get_workflow_state(self) -> WorkflowState:
        """Get the current state of the workflow suitable for checkpointing."""
        ...

    async def set_workflow_state(self, state: WorkflowState) -> None:
        """Set the state of the workflow from a checkpoint.

        Args:
            state: The state data to set for the workflow.
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
        self._shared_state: dict[str, Any] = {}
        self._executor_states: dict[str, dict[str, Any]] = {}
        self._iteration_count: int = 0
        self._max_iterations: int = 100

        # Streaming flag - set by workflow's run_stream() vs run()
        self._streaming: bool = False

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

    async def set_executor_state(self, executor_id: str, state: dict[str, Any]) -> None:
        self._executor_states[executor_id] = state

    async def get_executor_state(self, executor_id: str) -> dict[str, Any] | None:
        return self._executor_states.get(executor_id)

    def has_checkpointing(self) -> bool:
        return self._checkpoint_storage is not None

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

    def reset_for_new_run(self, workflow_shared_state: SharedState | None = None) -> None:
        self._messages.clear()
        # Clear any pending events (best-effort) by recreating the queue
        self._event_queue = asyncio.Queue()
        self._shared_state.clear()
        self._executor_states.clear()
        self._iteration_count = 0
        self._streaming = False  # Reset streaming flag
        if workflow_shared_state is not None and hasattr(workflow_shared_state, "_state"):
            workflow_shared_state._state.clear()  # type: ignore[attr-defined]

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        wf_id = self._workflow_id or str(uuid.uuid4())
        self._workflow_id = wf_id
        state = await self.get_workflow_state()

        checkpoint = WorkflowCheckpoint(
            workflow_id=wf_id,
            messages=state["messages"],
            shared_state=state.get("shared_state", {}),
            executor_states=state.get("executor_states", {}),
            iteration_count=state.get("iteration_count", 0),
            max_iterations=state.get("max_iterations", DEFAULT_MAX_ITERATIONS),
            metadata=metadata or {},
        )
        checkpoint_id = await self._checkpoint_storage.save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {checkpoint_id} for workflow {wf_id}'")
        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")
        return await self._checkpoint_storage.load_checkpoint(checkpoint_id)

    async def get_workflow_state(self) -> WorkflowState:
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
            "shared_state": encode_checkpoint_value(self._shared_state),
            "executor_states": encode_checkpoint_value(self._executor_states),
            "iteration_count": self._iteration_count,
            "max_iterations": self._max_iterations,
        }

    async def set_workflow_state(self, state: WorkflowState) -> None:
        self._messages.clear()
        messages_data = state.get("messages", {})
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
        # Restore shared_state
        decoded_shared_raw = decode_checkpoint_value(state.get("shared_state", {}))
        if isinstance(decoded_shared_raw, dict):
            self._shared_state = cast(dict[str, Any], decoded_shared_raw)
        else:  # fallback to empty dict if corrupted
            self._shared_state = {}

        # Restore executor_states ensuring value types are dicts
        decoded_exec_raw = decode_checkpoint_value(state.get("executor_states", {}))
        if isinstance(decoded_exec_raw, dict):
            typed_exec: dict[str, dict[str, Any]] = {}
            for k_raw, v_raw in decoded_exec_raw.items():  # type: ignore[assignment]
                if isinstance(k_raw, str) and isinstance(v_raw, dict):
                    # Filter inner dict to string keys only (best-effort)
                    inner: dict[str, Any] = {}
                    for inner_k, inner_v in v_raw.items():  # type: ignore[assignment]
                        if isinstance(inner_k, str):
                            inner[inner_k] = inner_v
                    typed_exec[k_raw] = inner
            self._executor_states = typed_exec
        else:
            self._executor_states = {}

        self._iteration_count = state.get("iteration_count", 0)
        self._max_iterations = state.get("max_iterations", 100)
