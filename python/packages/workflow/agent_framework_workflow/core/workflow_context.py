# Copyright (c) Microsoft. All rights reserved.

from collections import defaultdict
from typing import Any, Protocol, runtime_checkable

from .events import WorkflowEvent


@runtime_checkable
class WorkflowContext(Protocol):
    """Protocol for workflow context used by executors."""

    async def send_message(self, source_id: str, message: Any) -> None:
        """Send a message from the executor to the context.

        Args:
            source_id: The ID of the executor sending the message.
            message: The message to be sent.
        """
        ...

    async def drain_messages(self) -> dict[str, list[Any]]:
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


class InProcWorkflowContext(WorkflowContext):
    """In-process execution context for testing purposes."""

    def __init__(self):
        """Initialize the in-process execution context."""
        self._messages: defaultdict[str, list[Any]] = defaultdict(list)
        self._events: list[WorkflowEvent] = []

    async def send_message(self, source_id: str, message: Any) -> None:
        """Send a message from the executor to the context."""
        self._messages[source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Any]]:
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


class NoopWorkflowContext(WorkflowContext):
    """A no-operation execution context that does nothing."""

    async def send_message(self, source_id: str, message: Any) -> None:
        """Override to do nothing."""
        pass

    async def drain_messages(self) -> dict[str, list[Any]]:
        """Override to return an empty dictionary."""
        return {}

    async def has_messages(self) -> bool:
        """Override to always return False."""
        return False

    async def add_event(self, event: WorkflowEvent) -> None:
        """Override to do nothing."""
        pass

    async def drain_events(self) -> list[WorkflowEvent]:
        """Override to return an empty list."""
        return []

    async def has_events(self) -> bool:
        """Override to always return False."""
        return False
