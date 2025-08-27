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
    RequestResponse,
    SubWorkflowRequestInfo,
    SubWorkflowResponse,
    WorkflowExecutor,
    handler,
    intercepts_request,
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
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "RequestResponse",
    "RunnerContext",
    "SubWorkflowRequestInfo",
    "SubWorkflowResponse",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowEvent",
    "WorkflowExecutor",
    "WorkflowRunResult",
    "WorkflowStartedEvent",
    "WorkflowValidationError",
    "WorkflowViz",
    "__version__",
    "handler",
    "intercepts_request",
    "validate_workflow_graph",
]


# Rebuild models to resolve forward references after all imports are complete
import contextlib

with contextlib.suppress(AttributeError, TypeError, ValueError):
    # Rebuild WorkflowExecutor to resolve Workflow forward reference
    WorkflowExecutor.model_rebuild()
