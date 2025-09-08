# Copyright (c) Microsoft. All rights reserved.

"""Core actor abstractions for the Python actor runtime."""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, kw_only=True)
class ActorId:
    """Unique identifier for an actor instance."""

    type_name: str
    instance_id: str

    def __str__(self) -> str:
        """Return the string representation of the actor ID."""
        return f"{self.type_name}/{self.instance_id}"


class RequestStatus(Enum):
    """Status of a request being processed by an actor."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
