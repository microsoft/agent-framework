# Copyright (c) Microsoft. All rights reserved.

from ._agent import WorkflowAgent
from ._agent_executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
)
from ._base_group_chat_orchestrator import GroupChatRequestSentEvent, GroupChatResponseReceivedEvent
from ._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._checkpoint_summary import WorkflowCheckpointSummary, get_checkpoint_summary
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
    SuperStepCompletedEvent,
    SuperStepStartedEvent,
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowEventSource,
    WorkflowFailedEvent,
    WorkflowLifecycleEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
)
from ._executor import (
    Executor,
    handler,
)
from ._function_executor import FunctionExecutor, executor
from ._group_chat import (
    AgentBasedGroupChatOrchestrator,
    GroupChatBuilder,
    GroupChatState,
)
from ._handoff import HandoffBuilder

# from ._magentic import (
#     MAGENTIC_EVENT_TYPE_AGENT_DELTA,
#     MAGENTIC_EVENT_TYPE_ORCHESTRATOR,
#     ORCH_MSG_KIND_INSTRUCTION,
#     ORCH_MSG_KIND_NOTICE,
#     ORCH_MSG_KIND_TASK_LEDGER,
#     ORCH_MSG_KIND_USER_TASK,
#     MagenticBuilder,
#     MagenticContext,
#     MagenticHumanInputRequest,
#     MagenticHumanInterventionDecision,
#     MagenticHumanInterventionKind,
#     MagenticHumanInterventionReply,
#     MagenticHumanInterventionRequest,
#     MagenticManagerBase,
#     MagenticStallInterventionDecision,
#     MagenticStallInterventionReply,
#     MagenticStallInterventionRequest,
#     StandardMagenticManager,
# )
from ._orchestration_request_info import AgentRequestInfoResponse
from ._orchestration_state import OrchestrationState
from ._request_info_mixin import response_handler
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
from ._workflow_executor import SubWorkflowRequestMessage, SubWorkflowResponseMessage, WorkflowExecutor

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentBasedGroupChatOrchestrator",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentRequestInfoResponse",
    "AgentRequestInfoResponse",
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
    "ExecutorEvent",
    "ExecutorFailedEvent",
    "ExecutorInvokedEvent",
    "FanInEdgeGroup",
    "FanOutEdgeGroup",
    "FileCheckpointStorage",
    "FunctionExecutor",
    "GraphConnectivityError",
    "GroupChatBuilder",
    "GroupChatRequestSentEvent",
    "GroupChatResponseReceivedEvent",
    "GroupChatState",
    "HandoffBuilder",
    "HandoffBuilder",
    "InMemoryCheckpointStorage",
    "InProcRunnerContext",
    # "MagenticBuilder",
    # "MagenticContext",
    # "MagenticHumanInputRequest",
    # "MagenticHumanInterventionDecision",
    # "MagenticHumanInterventionKind",
    # "MagenticHumanInterventionReply",
    # "MagenticHumanInterventionRequest",
    # "MagenticManagerBase",
    # "MagenticStallInterventionDecision",
    # "MagenticStallInterventionReply",
    # "MagenticStallInterventionRequest",
    # "ManagerDirectiveModel",
    # "ManagerSelectionRequest",
    # "ManagerSelectionResponse",
    "Message",
    "OrchestrationState",
    "RequestInfoEvent",
    "Runner",
    "RunnerContext",
    "SequentialBuilder",
    "SharedState",
    "SingleEdgeGroup",
    # "StandardMagenticManager",
    "SubWorkflowRequestMessage",
    "SubWorkflowResponseMessage",
    "SuperStepCompletedEvent",
    "SuperStepStartedEvent",
    "SwitchCaseEdgeGroup",
    "SwitchCaseEdgeGroupCase",
    "SwitchCaseEdgeGroupDefault",
    "TypeCompatibilityError",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowAgent",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCheckpointSummary",
    "WorkflowContext",
    "WorkflowErrorDetails",
    "WorkflowEvent",
    "WorkflowEventSource",
    "WorkflowExecutor",
    "WorkflowFailedEvent",
    "WorkflowLifecycleEvent",
    "WorkflowOutputEvent",
    "WorkflowRunResult",
    "WorkflowRunState",
    "WorkflowStartedEvent",
    "WorkflowStatusEvent",
    "WorkflowValidationError",
    "WorkflowViz",
    "create_edge_runner",
    "executor",
    "get_checkpoint_summary",
    "handler",
    "response_handler",
    "validate_workflow_graph",
]
