# Copyright (c) Microsoft. All rights reserved.

"""Orchestration patterns for Microsoft Agent Framework.

This package provides high-level builders for common multi-agent workflow patterns:
- SequentialBuilder: Chain agents in sequence
- ConcurrentBuilder: Fan-out to multiple agents in parallel
- HandoffBuilder: Decentralized agent routing
- GroupChatBuilder: Orchestrator-directed multi-agent conversations
- MagenticBuilder: Magentic One pattern for sophisticated multi-agent orchestration
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

from agent_framework import register_checkpoint_type

from ._base_group_chat_orchestrator import (
    BaseGroupChatOrchestrator,
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatRequestSentEvent,
    GroupChatResponseMessage,
    GroupChatResponseReceivedEvent,
    TerminationCondition,
)
from ._concurrent import ConcurrentBuilder
from ._group_chat import (
    AgentBasedGroupChatOrchestrator,
    AgentOrchestrationOutput,
    GroupChatBuilder,
    GroupChatOrchestrator,
    GroupChatSelectionFunction,
    GroupChatState,
)
from ._handoff import (
    HandoffAgentExecutor,
    HandoffAgentUserRequest,
    HandoffBuilder,
    HandoffConfiguration,
    HandoffSentEvent,
)
from ._magentic import (
    MAGENTIC_MANAGER_NAME,
    ORCH_MSG_KIND_INSTRUCTION,
    ORCH_MSG_KIND_NOTICE,
    ORCH_MSG_KIND_TASK_LEDGER,
    ORCH_MSG_KIND_USER_TASK,
    MagenticAgentExecutor,
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    MagenticOrchestrator,
    MagenticOrchestratorEvent,
    MagenticOrchestratorEventType,
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    MagenticResetSignal,
    StandardMagenticManager,
    _MagenticTaskLedger,
)
from ._orchestration_request_info import AgentRequestInfoResponse
from ._orchestration_state import OrchestrationState
from ._orchestrator_helpers import clean_conversation_for_handoff, create_completion_message
from ._sequential import SequentialBuilder

__all__ = [
    "MAGENTIC_MANAGER_NAME",
    "ORCH_MSG_KIND_INSTRUCTION",
    "ORCH_MSG_KIND_NOTICE",
    "ORCH_MSG_KIND_TASK_LEDGER",
    "ORCH_MSG_KIND_USER_TASK",
    "AgentBasedGroupChatOrchestrator",
    "AgentOrchestrationOutput",
    "AgentRequestInfoResponse",
    "BaseGroupChatOrchestrator",
    "ConcurrentBuilder",
    "GroupChatBuilder",
    "GroupChatOrchestrator",
    "GroupChatRequestMessage",
    "GroupChatRequestSentEvent",
    "GroupChatResponseReceivedEvent",
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
    "OrchestrationState",
    "SequentialBuilder",
    "StandardMagenticManager",
    "TerminationCondition",
    "__version__",
    "clean_conversation_for_handoff",
    "create_completion_message",
]

# Framework-owned types that cross a checkpoint boundary: executor-to-executor message
# envelopes and request_info payloads/responses. Registering them here means built-in
# orchestrations restore without users maintaining their own `allowed_checkpoint_types`
# list of framework module paths.
for _checkpoint_type in (
    GroupChatRequestMessage,
    GroupChatParticipantMessage,
    GroupChatResponseMessage,
    HandoffAgentUserRequest,
    AgentRequestInfoResponse,
    MagenticResetSignal,
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    _MagenticTaskLedger,
):
    register_checkpoint_type(_checkpoint_type)

del _checkpoint_type
