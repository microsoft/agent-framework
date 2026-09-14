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


# Framework-owned types that cross a checkpoint boundary.
#
# Checkpoint restore runs pickle through a restricted unpickler whose default allowlist
# auto-trusts the ``agent_framework.`` prefix. That prefix is dotted, so it covers core but
# not sibling distributions such as this one -- deliberately, since dropping the dot would
# auto-trust any installed package merely named ``agent_framework_*``. Built-in orchestration
# envelopes therefore have to opt in by name, or users have to hand-maintain
# ``allowed_checkpoint_types`` with framework-internal module paths (#7789).
#
# Each entry below crosses the boundary for a stated reason. Nothing belongs here that only
# travels as a dict: ``_MagenticTaskLedger``, for instance, is persisted through
# ``to_dict()``/``from_dict()`` and never reaches the unpickler.
for _checkpoint_type in (
    # Executor-to-executor message envelopes.
    GroupChatRequestMessage,
    GroupChatParticipantMessage,
    GroupChatResponseMessage,
    MagenticResetSignal,
    # ``request_info`` payloads and their response types, which are checkpointed as
    # pending request-info events while a workflow waits on a human.
    HandoffAgentUserRequest,
    AgentRequestInfoResponse,
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
    # Nested inside ``MagenticPlanReviewRequest.current_progress``. The unpickler resolves
    # nested classes too, so registering only the outer request is not enough.
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
):
    register_checkpoint_type(_checkpoint_type)

del _checkpoint_type
