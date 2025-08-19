# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, TypeVar, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
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


class CheckpointState(TypedDict):
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

    async def set_state(self, executor_id: str, state: dict[str, Any]) -> None:
        """Set the state for a specific executor.

        Args:
            executor_id: The ID of the executor whose state is being set.
            state: The state data to be set for the executor.
        """
        ...

    async def get_state(self, executor_id: str) -> dict[str, Any] | None:
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

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        """Create a checkpoint of the current workflow state.

        Args:
            metadata: Optional metadata to associate with the checkpoint.
        """
        ...

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore the context from a checkpoint.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from.

        Returns:
            True if the restoration was successful, False otherwise.
        """
        ...

    async def get_checkpoint_state(self) -> CheckpointState:
        """Get the current state of the context suitable for checkpointing."""
        ...

    async def set_checkpoint_state(self, state: CheckpointState) -> None:
        """Set the state of the context from a checkpoint.

        Args:
            state: The state data to set for the context.
        """
        ...


class InProcRunnerContext:
    """In-process execution context for local execution and optional checkpointing."""

    def __init__(self, checkpoint_storage: CheckpointStorage | None = None):
        """Initialize the in-process execution context.

        Args:
            checkpoint_storage: Optional storage to enable checkpointing.
        """
        self._messages: defaultdict[str, list[Message]] = defaultdict(list)
        self._events: list[WorkflowEvent] = []

        # Checkpointing configuration/state
        self._checkpoint_storage = checkpoint_storage
        self._workflow_id: str | None = None
        self._shared_state: dict[str, Any] = {}
        self._executor_states: dict[str, dict[str, Any]] = {}
        self._iteration_count: int = 0
        self._max_iterations: int = 100

    async def send_message(self, message: Message) -> None:
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
        messages = dict(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        return bool(self._messages)

    async def add_event(self, event: WorkflowEvent) -> None:
        self._events.append(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        events = self._events.copy()
        self._events.clear()
        return events

    async def has_events(self) -> bool:
        return bool(self._events)

    async def set_state(self, executor_id: str, state: dict[str, Any]) -> None:
        self._executor_states[executor_id] = state

    async def get_state(self, executor_id: str) -> dict[str, Any] | None:
        return self._executor_states.get(executor_id)

    def has_checkpointing(self) -> bool:
        return self._checkpoint_storage is not None

    def set_workflow_id(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id

    def reset_for_new_run(self, workflow_shared_state: "SharedState | None" = None) -> None:
        self._messages.clear()
        self._events.clear()
        self._shared_state.clear()
        self._executor_states.clear()
        self._iteration_count = 0
        if workflow_shared_state is not None and hasattr(workflow_shared_state, "_state"):
            workflow_shared_state._state.clear()  # type: ignore[attr-defined]

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        wf_id = self._workflow_id or str(uuid.uuid4())
        self._workflow_id = wf_id
        state = await self.get_checkpoint_state()

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

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        checkpoint = await self._checkpoint_storage.load_checkpoint(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint {checkpoint_id} not found")
            return False

        state: CheckpointState = {
            "messages": checkpoint.messages,
            "shared_state": checkpoint.shared_state,
            "executor_states": checkpoint.executor_states,
            "iteration_count": checkpoint.iteration_count,
            "max_iterations": checkpoint.max_iterations,
        }
        await self.set_checkpoint_state(state)
        self._workflow_id = checkpoint.workflow_id
        logger.info(f"Restored state from checkpoint {checkpoint_id}'")
        return True

    async def get_checkpoint_state(self) -> CheckpointState:
        serializable_messages: dict[str, list[dict[str, Any]]] = {}
        for source_id, message_list in self._messages.items():
            serializable_messages[source_id] = [
                {"data": msg.data, "source_id": msg.source_id, "target_id": msg.target_id} for msg in message_list
            ]
        return {
            "messages": serializable_messages,
            "shared_state": self._shared_state,
            "executor_states": self._executor_states,
            "iteration_count": self._iteration_count,
            "max_iterations": self._max_iterations,
        }

    async def set_checkpoint_state(self, state: CheckpointState) -> None:
        self._messages.clear()
        messages_data = state.get("messages", {})
        for source_id, message_list in messages_data.items():
            self._messages[source_id] = [
                Message(
                    data=msg.get("data"),
                    source_id=msg.get("source_id", ""),
                    target_id=msg.get("target_id"),
                )
                for msg in message_list
            ]
        self._shared_state = state.get("shared_state", {})
        self._executor_states = state.get("executor_states", {})
        self._iteration_count = state.get("iteration_count", 0)
        self._max_iterations = state.get("max_iterations", 100)
