# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._events import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    ExecutorCompleteEvent,
    ExecutorEvent,
    ExecutorInvokeEvent,
    RequestInfoEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowStartedEvent,
)
from ._executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    message_handler,
)
from ._validation import (
    EdgeDuplicationError,
    GraphConnectivityError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowValidationError,
    validate_workflow_graph,
)
from ._workflow import WorkflowBuilder
from ._workflow_context import WorkflowContext

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


__all__ = [
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentRunEvent",
    "AgentRunStreamingEvent",
    "EdgeDuplicationError",
    "Executor",
    "ExecutorCompleteEvent",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "GraphConnectivityError",
    "RequestInfoEvent",
    "RequestInfoEvent",
    "RequestInfoExecutor",
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "WorkflowBuilder",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowEvent",
    "WorkflowStartedEvent",
    "WorkflowValidationError",
    "__version__",
    "message_handler",
    "validate_workflow_graph",
]
