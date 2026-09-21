# Copyright (c) Microsoft. All rights reserved.

"""Execution-state helpers for app-owned Agent Framework hosting routes."""

import importlib.metadata

from ._state import (
    AgentRunArgs,
    AgentState,
    SupportsBuild,
    WorkflowRunArgs,
    WorkflowState,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AgentRunArgs",
    "AgentState",
    "SupportsBuild",
    "WorkflowRunArgs",
    "WorkflowState",
    "__version__",
]
