# Copyright (c) Microsoft. All rights reserved.

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

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
