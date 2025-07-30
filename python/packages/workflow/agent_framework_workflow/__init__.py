# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._events import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    ExecutorCompleteEvent,
    ExecutorEvent,
    ExecutorInvokeEvent,
    HumanInTheLoopEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowStartedEvent,
)
from ._executor import Executor, output_message_types
from ._workflow import WorkflowBuilder
from ._workflow_context import WorkflowContext

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


__all__ = [
    "AgentRunEvent",
    "AgentRunStreamingEvent",
    "Executor",
    "ExecutorCompleteEvent",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "HumanInTheLoopEvent",
    "WorkflowBuilder",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowEvent",
    "WorkflowStartedEvent",
    "__version__",
    "output_message_types",
]
