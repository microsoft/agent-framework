# Copyright (c) Microsoft. All rights reserved.

"""Custom exception types for the durable agent framework."""

from __future__ import annotations


class IncomingRequestError(ValueError):
    """Raised when an incoming HTTP request cannot be parsed or validated."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
