# Copyright (c) Microsoft. All rights reserved.

# Default maximum iterations for workflow execution.
DEFAULT_MAX_ITERATIONS = 100

# Key used to store executor state in shared state.
EXECUTOR_STATE_KEY = "_executor_state"

# Source identifier for internal workflow messages.
INTERNAL_SOURCE_PREFIX = "internal"


def INTERNAL_SOURCE_ID(executor_id: str) -> str:
    """Generate an internal source ID for a given executor."""
    return f"{INTERNAL_SOURCE_PREFIX}:{executor_id}"
