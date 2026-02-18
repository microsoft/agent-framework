# Copyright (c) Microsoft. All rights reserved.

"""Workflow namespace for built-in Agent Framework orchestration primitives.

This module re-exports objects from workflow implementation modules under
``agent_framework._workflows``.

Supported classes include:
- Workflow
- WorkflowBuilder
- AgentExecutor
- Runner
- WorkflowExecutor
"""

from ._agent import WorkflowAgent
from ._agent_executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
)
from ._agent_utils import resolve_agent_id
from ._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._checkpoint_encoding import (
    decode_checkpoint_value,
    encode_checkpoint_value,
)
from ._const import (
    DEFAULT_MAX_ITERATIONS,
)
from ._edge import (
    Case,
    Default,
    Edge,
    EdgeCondition,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from ._edge_runner import create_edge_runner
from ._events import (
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowEventSource,
    WorkflowEventType,
    WorkflowRunState,
)
from ._exceptions import (
    WorkflowCheckpointException,
    WorkflowConvergenceException,
    WorkflowException,
    WorkflowRunnerException,
)
from ._executor import (
    Executor,
    handler,
)
from ._function_executor import FunctionExecutor, executor
from ._request_info_mixin import response_handler
from ._runner import Runner
from ._runner_context import (
    InProcRunnerContext,
    RunnerContext,
    WorkflowMessage,
)
from ._state import State
from ._validation import (
    EdgeDuplicationError,
    GraphConnectivityError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowValidationError,
    validate_workflow_graph,
)
from ._viz import WorkflowViz
from ._workflow import Workflow, WorkflowRunResult
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext
from ._workflow_executor import (
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    WorkflowExecutor,
)

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "Case",
    "CheckpointStorage",
    "Default",
    "Edge",
    "EdgeCondition",
    "EdgeDuplicationError",
    "Executor",
    "FanInEdgeGroup",
    "FanOutEdgeGroup",
    "FileCheckpointStorage",
    "FunctionExecutor",
    "GraphConnectivityError",
    "InMemoryCheckpointStorage",
    "InProcRunnerContext",
    "Runner",
    "RunnerContext",
    "SingleEdgeGroup",
    "State",
    "SubWorkflowRequestMessage",
    "SubWorkflowResponseMessage",
    "SwitchCaseEdgeGroup",
    "SwitchCaseEdgeGroupCase",
    "SwitchCaseEdgeGroupDefault",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowAgent",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCheckpointException",
    "WorkflowContext",
    "WorkflowConvergenceException",
    "WorkflowErrorDetails",
    "WorkflowEvent",
    "WorkflowEventSource",
    "WorkflowEventType",
    "WorkflowException",
    "WorkflowExecutor",
    "WorkflowMessage",
    "WorkflowRunResult",
    "WorkflowRunState",
    "WorkflowRunnerException",
    "WorkflowValidationError",
    "WorkflowViz",
    "create_edge_runner",
    "decode_checkpoint_value",
    "encode_checkpoint_value",
    "executor",
    "handler",
    "resolve_agent_id",
    "response_handler",
    "validate_workflow_graph",
]
