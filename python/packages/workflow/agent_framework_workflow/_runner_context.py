# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._events import WorkflowEvent

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Message:
    """A class representing a message in the workflow."""

    data: Any
    source_id: str
    target_id: str | None = None


@runtime_checkable
class RunnerContext(Protocol):
    """Protocol for the execution context used by the runner."""

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


class InProcRunnerContext(RunnerContext):
    """In-process execution context for local execution of workflows."""

    def __init__(self):
        """Initialize the in-process execution context."""
        self._messages: defaultdict[str, list[Message]] = defaultdict(list)
        self._events: list[WorkflowEvent] = []

    async def send_message(self, message: Message) -> None:
        """Send a message from the executor to the context."""
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
        """Drain all messages from the context."""
        messages = dict(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        """Check if there are any messages in the context."""
        return bool(self._messages)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the execution context.

        Args:
            event: The event to be added.
        """
        self._events.append(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all events from the context."""
        events = self._events.copy()
        self._events.clear()
        return events

    async def has_events(self) -> bool:
        """Check if there are any events in the context."""
        return bool(self._events)


class CheckpointableInProcRunnerContext(InProcRunnerContext):
    """In-process execution context with checkpointing capabilities."""

    def __init__(self, checkpoint_storage: CheckpointStorage | None = None):
        """Initialize the checkpointable in-process execution context."""
        super().__init__()
        self._checkpoint_storage = checkpoint_storage
        self._workflow_id: str | None = None

    def set_workflow_id(self, workflow_id: str) -> None:
        """Set the workflow ID for this context."""
        self._workflow_id = workflow_id

    async def create_checkpoint(self, workflow_id: str | None = None) -> str:
        """Create a checkpoint of current state."""
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        # Use provided workflow_id or the stored one, generate once if neither exists
        if workflow_id:
            wf_id = workflow_id
            self._workflow_id = workflow_id  # Store for future use
        elif self._workflow_id:
            wf_id = self._workflow_id
        else:
            wf_id = str(uuid.uuid4())
            self._workflow_id = wf_id  # Store for future use

        # Get current state
        state = await self.get_checkpoint_state()

        # Create checkpoint
        checkpoint = WorkflowCheckpoint(
            workflow_id=wf_id,
            messages=cast(dict[str, list[dict[str, Any]]], state["messages"]),
            events=cast(list[dict[str, Any]], state["events"]),
            shared_state=cast(dict[str, Any], state.get("shared_state", {})),
            executor_states=cast(dict[str, dict[str, Any]], state.get("executor_states", {})),
            iteration_count=cast(int, state.get("iteration_count", 0)),
            max_iterations=cast(int, state.get("max_iterations", 100)),
        )

        # Save checkpoint
        checkpoint_id = self._checkpoint_storage.save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {checkpoint_id} for workflow {wf_id}")
        return checkpoint_id

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore state from checkpoint."""
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        # Load checkpoint
        checkpoint = self._checkpoint_storage.load_checkpoint(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint {checkpoint_id} not found")
            return False

        # Restore state
        state = {
            "messages": checkpoint.messages,
            "events": checkpoint.events,
            "shared_state": checkpoint.shared_state,
            "executor_states": checkpoint.executor_states,
            "iteration_count": checkpoint.iteration_count,
            "max_iterations": checkpoint.max_iterations,
        }

        await self.set_checkpoint_state(cast(dict[str, object], state))
        # TODO(evmattso): should we reuse the same workflow_id from checkpoint
        # or generate a new one when resuming? Current behavior maintains logical continuity
        # but may cause issues with parallel executions from same checkpoint.
        self._workflow_id = checkpoint.workflow_id

        logger.info(f"Restored state from checkpoint {checkpoint_id}")
        return True

    async def get_checkpoint_state(self) -> dict[str, object]:
        """Get serializable state for checkpointing."""
        # Convert messages to serializable format
        serializable_messages = {}
        for source_id, message_list in self._messages.items():
            serializable_messages[source_id] = [
                {
                    "data": msg.data,
                    "source_id": msg.source_id,
                    "target_id": msg.target_id,
                }
                for msg in message_list
            ]

        # Convert events to serializable format
        serializable_events: list[dict[str, object]] = []
        for event in self._events:
            event_dict: dict[str, object] = {
                "type": event.__class__.__name__,
                "data": getattr(event, "__dict__", {}),
            }
            # For workflow completion events, include the data directly
            if hasattr(event, "data"):
                event_dict["result"] = event.data
            serializable_events.append(event_dict)

        return {
            "messages": serializable_messages,
            "events": serializable_events,
        }

    async def set_checkpoint_state(self, state: dict[str, object]) -> None:
        """Restore state from checkpoint data."""
        # Restore messages
        self._messages.clear()
        messages_data = cast(dict[str, list[dict[str, object]]], state.get("messages", {}))
        for source_id, message_list in messages_data.items():
            self._messages[source_id] = [
                Message(
                    data=msg.get("data"),
                    source_id=cast(str, msg.get("source_id", "")),
                    target_id=cast(str | None, msg.get("target_id")),
                )
                for msg in message_list
            ]

        # Restore events (simplified - in practice, we'd need to reconstruct event objects)
        self._events.clear()
        events_data = cast(list[dict[str, object]], state.get("events", []))
        for event_data in events_data:
            # For now, store as a generic event placeholder
            # In a full implementation, we'd reconstruct proper event objects
            logger.debug(f"Restored event: {event_data}")
