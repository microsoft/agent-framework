# Copyright (c) Microsoft. All rights reserved.

from enum import Enum

# TODO (dmytrostruk): Think about naming, "Status" seems too generic.


class Status(str, Enum):
    """Status enum."""

    COMPLETED = "completed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    INCOMPLETE = "incomplete"
