# Copyright (c) Microsoft. All rights reserved.

import contextlib

from ._agent import WorkflowAgent
from ._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._concurrent import ConcurrentBuilder
from ._const import (
    DEFAULT_MAX_ITERATIONS,
)
from ._edge import (
    Case,
    Default,
    Edge,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from ._edge_runner import create_edge_runner
from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,
    ExecutorCompletedEvent,
    ExecutorEvent,
    ExecutorFailedEvent,
    ExecutorInvokedEvent,
    RequestInfoEvent,
    WorkflowCompletedEvent,
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowEventSource,
    WorkflowFailedEvent,
    WorkflowLifecycleEvent,
    WorkflowRunState,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
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
from ._magentic import (
    MagenticAgentDeltaEvent,
    MagenticAgentExecutor,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticCallbackEvent,
    MagenticCallbackMode,
    MagenticContext,
    MagenticFinalResultEvent,
    MagenticManagerBase,
    MagenticOrchestratorExecutor,
    MagenticOrchestratorMessageEvent,
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
from ._runner import Runner
from ._runner_context import (
    InProcRunnerContext,
    Message,
    RunnerContext,
)
from ._sequential import SequentialBuilder
from ._shared_state import SharedState
from ._validation import (
    EdgeDuplicationError,
    ExecutorDuplicationError,
    GraphConnectivityError,
    HandlerOutputAnnotationError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowValidationError,
    validate_workflow_graph,
)
from ._viz import WorkflowViz
from ._workflow import Workflow, WorkflowBuilder, WorkflowRunResult
from ._workflow_context import WorkflowContext

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentRunEvent",
    "AgentRunUpdateEvent",
    "Case",
    "CheckpointStorage",
    "ConcurrentBuilder",
    "Default",
    "Edge",
    "EdgeDuplicationError",
    "Executor",
    "ExecutorCompletedEvent",
    "ExecutorDuplicationError",
    "ExecutorEvent",
    "ExecutorFailedEvent",
    "ExecutorInvokedEvent",
    "FanInEdgeGroup",
    "FanOutEdgeGroup",
    "FileCheckpointStorage",
    "FunctionExecutor",
    "GraphConnectivityError",
    "HandlerOutputAnnotationError",
    "InMemoryCheckpointStorage",
    "InProcRunnerContext",
    "MagenticAgentDeltaEvent",
    "MagenticAgentExecutor",
    "MagenticAgentMessageEvent",
    "MagenticBuilder",
    "MagenticCallbackEvent",
    "MagenticCallbackMode",
    "MagenticContext",
    "MagenticFinalResultEvent",
    "MagenticManagerBase",
    "MagenticOrchestratorExecutor",
    "MagenticOrchestratorMessageEvent",
    "MagenticPlanReviewDecision",
    "MagenticPlanReviewReply",
    "MagenticPlanReviewRequest",
    "MagenticProgressLedger",
    "MagenticProgressLedgerItem",
    "MagenticRequestMessage",
    "MagenticResponseMessage",
    "MagenticStartMessage",
    "Message",
    "RequestInfoEvent",
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "RequestResponse",
    "Runner",
    "RunnerContext",
    "SequentialBuilder",
    "SharedState",
    "SingleEdgeGroup",
    "StandardMagenticManager",
    "SubWorkflowRequestInfo",
    "SubWorkflowResponse",
    "SwitchCaseEdgeGroup",
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
    "WorkflowErrorDetails",
    "WorkflowEvent",
    "WorkflowEventSource",
    "WorkflowExecutor",
    "WorkflowFailedEvent",
    "WorkflowLifecycleEvent",
    "WorkflowRunResult",
    "WorkflowRunState",
    "WorkflowStartedEvent",
    "WorkflowStatusEvent",
    "WorkflowValidationError",
    "WorkflowViz",
    "create_edge_runner",
    "executor",
    "handler",
    "intercepts_request",
    "validate_workflow_graph",
]

# Rebuild models to resolve forward references after all imports are complete
with contextlib.suppress(AttributeError, TypeError, ValueError):
    # Rebuild WorkflowExecutor to resolve Workflow forward reference
    WorkflowExecutor.model_rebuild()
    # Rebuild WorkflowAgent to resolve Workflow forward reference
    WorkflowAgent.model_rebuild()
