# Copyright (c) Microsoft. All rights reserved.

"""Ticketing plugin for CustomerSupport workflow."""

import uuid
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable

# ANSI color codes
MAGENTA = "\033[35m"
RESET = "\033[0m"


class TicketStatus(Enum):
    """Status of a support ticket."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class TicketItem:
    """A support ticket."""

    id: str
    subject: str = ""
    description: str = ""
    notes: str = ""
    status: TicketStatus = TicketStatus.OPEN


class TicketingPlugin:
    """Mock ticketing plugin for customer support workflow."""

    def __init__(self) -> None:
        self._ticket_store: dict[str, TicketItem] = {}

    def _trace(self, function_name: str) -> None:
        print(f"\n{MAGENTA}FUNCTION: {function_name}{RESET}")

    def get_ticket(self, id: str) -> TicketItem | None:
        """Retrieve a ticket by identifier from Azure DevOps."""
        self._trace("get_ticket")
        return self._ticket_store.get(id)

    def create_ticket(self, subject: str, description: str, notes: str) -> str:
        """Create a ticket in Azure DevOps and return its identifier."""
        self._trace("create_ticket")
        ticket_id = uuid.uuid4().hex
        ticket = TicketItem(
            id=ticket_id,
            subject=subject,
            description=description,
            notes=notes,
        )
        self._ticket_store[ticket_id] = ticket
        return ticket_id

    def resolve_ticket(self, id: str, resolution_summary: str) -> None:
        """Resolve an existing ticket in Azure DevOps given its identifier."""
        self._trace("resolve_ticket")
        if ticket := self._ticket_store.get(id):
            ticket.status = TicketStatus.RESOLVED

    def send_notification(self, id: str, email: str, cc: str, body: str) -> None:
        """Send an email notification to escalate ticket engagement."""
        self._trace("send_notification")

    def get_functions(self) -> list[Callable[..., object]]:
        """Return all plugin functions for registration."""
        return [
            self.get_ticket,
            self.create_ticket,
            self.resolve_ticket,
            self.send_notification,
        ]
