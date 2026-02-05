# Copyright (c) Microsoft. All rights reserved.

# Type stubs for lazy-loaded orchestrations module
# These re-export types from agent_framework_orchestrations

from agent_framework_orchestrations import (
    # Magentic
    MAGENTIC_MANAGER_NAME as MAGENTIC_MANAGER_NAME,
)
from agent_framework_orchestrations import (
    ORCH_MSG_KIND_INSTRUCTION as ORCH_MSG_KIND_INSTRUCTION,
)
from agent_framework_orchestrations import (
    ORCH_MSG_KIND_NOTICE as ORCH_MSG_KIND_NOTICE,
)
from agent_framework_orchestrations import (
    ORCH_MSG_KIND_TASK_LEDGER as ORCH_MSG_KIND_TASK_LEDGER,
)
from agent_framework_orchestrations import (
    ORCH_MSG_KIND_USER_TASK as ORCH_MSG_KIND_USER_TASK,
)
from agent_framework_orchestrations import (
    # Group Chat
    AgentBasedGroupChatOrchestrator as AgentBasedGroupChatOrchestrator,
)
from agent_framework_orchestrations import (
    AgentOrchestrationOutput as AgentOrchestrationOutput,
)
from agent_framework_orchestrations import (
    # Concurrent
    ConcurrentBuilder as ConcurrentBuilder,
)
from agent_framework_orchestrations import (
    GroupChatBuilder as GroupChatBuilder,
)
from agent_framework_orchestrations import (
    GroupChatOrchestrator as GroupChatOrchestrator,
)
from agent_framework_orchestrations import (
    GroupChatSelectionFunction as GroupChatSelectionFunction,
)
from agent_framework_orchestrations import (
    GroupChatState as GroupChatState,
)
from agent_framework_orchestrations import (
    # Handoff
    HandoffAgentExecutor as HandoffAgentExecutor,
)
from agent_framework_orchestrations import (
    HandoffAgentUserRequest as HandoffAgentUserRequest,
)
from agent_framework_orchestrations import (
    HandoffBuilder as HandoffBuilder,
)
from agent_framework_orchestrations import (
    HandoffConfiguration as HandoffConfiguration,
)
from agent_framework_orchestrations import (
    HandoffSentEvent as HandoffSentEvent,
)
from agent_framework_orchestrations import (
    MagenticAgentExecutor as MagenticAgentExecutor,
)
from agent_framework_orchestrations import (
    MagenticBuilder as MagenticBuilder,
)
from agent_framework_orchestrations import (
    MagenticContext as MagenticContext,
)
from agent_framework_orchestrations import (
    MagenticManagerBase as MagenticManagerBase,
)
from agent_framework_orchestrations import (
    MagenticOrchestrator as MagenticOrchestrator,
)
from agent_framework_orchestrations import (
    MagenticOrchestratorEvent as MagenticOrchestratorEvent,
)
from agent_framework_orchestrations import (
    MagenticOrchestratorEventType as MagenticOrchestratorEventType,
)
from agent_framework_orchestrations import (
    MagenticPlanReviewRequest as MagenticPlanReviewRequest,
)
from agent_framework_orchestrations import (
    MagenticPlanReviewResponse as MagenticPlanReviewResponse,
)
from agent_framework_orchestrations import (
    MagenticProgressLedger as MagenticProgressLedger,
)
from agent_framework_orchestrations import (
    MagenticProgressLedgerItem as MagenticProgressLedgerItem,
)
from agent_framework_orchestrations import (
    MagenticResetSignal as MagenticResetSignal,
)
from agent_framework_orchestrations import (
    # Sequential
    SequentialBuilder as SequentialBuilder,
)
from agent_framework_orchestrations import (
    StandardMagenticManager as StandardMagenticManager,
)
from agent_framework_orchestrations import (
    __version__ as __version__,
)

__all__ = [
    "MAGENTIC_MANAGER_NAME",
    "ORCH_MSG_KIND_INSTRUCTION",
    "ORCH_MSG_KIND_NOTICE",
    "ORCH_MSG_KIND_TASK_LEDGER",
    "ORCH_MSG_KIND_USER_TASK",
    "AgentBasedGroupChatOrchestrator",
    "AgentOrchestrationOutput",
    "ConcurrentBuilder",
    "GroupChatBuilder",
    "GroupChatOrchestrator",
    "GroupChatSelectionFunction",
    "GroupChatState",
    "HandoffAgentExecutor",
    "HandoffAgentUserRequest",
    "HandoffBuilder",
    "HandoffConfiguration",
    "HandoffSentEvent",
    "MagenticAgentExecutor",
    "MagenticBuilder",
    "MagenticContext",
    "MagenticManagerBase",
    "MagenticOrchestrator",
    "MagenticOrchestratorEvent",
    "MagenticOrchestratorEventType",
    "MagenticPlanReviewRequest",
    "MagenticPlanReviewResponse",
    "MagenticProgressLedger",
    "MagenticProgressLedgerItem",
    "MagenticResetSignal",
    "SequentialBuilder",
    "StandardMagenticManager",
    "__version__",
]
