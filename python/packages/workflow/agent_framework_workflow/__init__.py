# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from .core import events
from .core.events import (
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
from .core.executor import Executor, ExecutorContext, output_message_types
from .core.workflow import WorkflowBuilder

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


__all__ = [
    "AgentRunEvent",
    "AgentRunStreamingEvent",
    "Executor",
    "ExecutorCompleteEvent",
    "ExecutorContext",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "HumanInTheLoopEvent",
    "WorkflowBuilder",
    "WorkflowCompletedEvent",
    "WorkflowEvent",
    "WorkflowStartedEvent",
    "__version__",
    "events",
    "output_message_types",
]
