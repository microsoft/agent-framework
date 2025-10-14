# Copyright (c) Microsoft. All rights reserved.

DEFAULT_MAX_ITERATIONS = 100  # Default maximum iterations for workflow execution.

INTERNAL_SOURCE_PREFIX = "internal"  # Source identifier for internal workflow messages.


def INTERNAL_SOURCE_ID(executor_id: str) -> str:
    """Generate an internal source ID for a given executor."""
    return f"{INTERNAL_SOURCE_PREFIX}:{executor_id}"
