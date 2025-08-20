# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._const import (
    DEFAULT_MAX_ITERATIONS,
)
from ._edge import Case, Default
from ._events import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    ExecutorCompletedEvent,
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
    handler,
)
from ._runner_context import (
    InProcRunnerContext,
    Message,
    RunnerContext,
)
from ._validation import (
    EdgeDuplicationError,
    GraphConnectivityError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowValidationError,
    validate_workflow_graph,
)
from ._viz import WorkflowViz
from ._workflow import Workflow, WorkflowBuilder, WorkflowRunResult
from ._workflow_context import WorkflowContext

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentRunEvent",
    "AgentRunStreamingEvent",
    "Case",
    "CheckpointStorage",
    "Default",
    "EdgeDuplicationError",
    "Executor",
    "ExecutorCompletedEvent",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "FileCheckpointStorage",
    "GraphConnectivityError",
    "InMemoryCheckpointStorage",
    "InProcRunnerContext",
    "Message",
    "RequestInfoEvent",
    "RequestInfoEvent",
    "RequestInfoExecutor",
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "RunnerContext",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowEvent",
    "WorkflowRunResult",
    "WorkflowStartedEvent",
    "WorkflowValidationError",
    "WorkflowViz",
    "__version__",
    "handler",
    "validate_workflow_graph",
]
