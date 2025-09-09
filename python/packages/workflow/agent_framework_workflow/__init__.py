# Copyright (c) Microsoft. All rights reserved.

import contextlib
import importlib.metadata

from ._agent import WorkflowAgent
from ._callback import (
    AgentDeltaEvent,
    AgentMessageEvent,
    CallbackEvent,
    CallbackMode,
    FinalResultEvent,
    OrchestratorMessageEvent,
)
from ._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import (
    Case,
    Default,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,
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
from ._function_executor import FunctionExecutor, executor
from ._handoff import HandoffAction, HandoffBuilder, HandoffDecision
from ._magentic import (
    MagenticAgentExecutor,
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    MagenticOrchestratorExecutor,
    MagenticPlanReviewDecision,
    MagenticPlanReviewReply,
    MagenticPlanReviewRequest,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    MagenticRequestMessage,
    MagenticResponseMessage,
    MagenticStartMessage,
    StandardMagenticManager,
)
from ._runner_context import InProcRunnerContext, Message, RunnerContext
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
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentDeltaEvent",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentMessageEvent",
    "AgentRunEvent",
    "AgentRunUpdateEvent",
    "CallbackEvent",
    "CallbackMode",
    "Case",
    "CheckpointStorage",
    "Default",
    "EdgeDuplicationError",
    "Executor",
    "ExecutorCompletedEvent",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "FileCheckpointStorage",
    "FinalResultEvent",
    "FunctionExecutor",
    "GraphConnectivityError",
    "HandoffAction",
    "HandoffBuilder",
    "HandoffDecision",
    "InMemoryCheckpointStorage",
    "InProcRunnerContext",
    "MagenticAgentExecutor",
    "MagenticBuilder",
    "MagenticContext",
    "MagenticManagerBase",
    "MagenticOrchestratorExecutor",
    "MagenticPlanReviewDecision",
    "MagenticPlanReviewReply",
    "MagenticPlanReviewRequest",
    "MagenticProgressLedger",
    "MagenticProgressLedgerItem",
    "MagenticRequestMessage",
    "MagenticResponseMessage",
    "MagenticStartMessage",
    "Message",
    "OrchestratorMessageEvent",
    "RequestInfoEvent",
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "RequestResponse",
    "RunnerContext",
    "StandardMagenticManager",
    "SubWorkflowRequestInfo",
    "SubWorkflowResponse",
    "SwitchCaseEdgeGroupCase",
    "SwitchCaseEdgeGroupDefault",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowAgent",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowEvent",
    "WorkflowExecutor",
    "WorkflowRunResult",
    "WorkflowRunResult",
    "WorkflowStartedEvent",
    "WorkflowValidationError",
    "WorkflowViz",
    "__version__",
    "executor",
    "handler",
    "intercepts_request",
    "validate_workflow_graph",
]

with contextlib.suppress(AttributeError, TypeError, ValueError):  # pragma: no cover
    WorkflowExecutor.model_rebuild()
    WorkflowAgent.model_rebuild()
