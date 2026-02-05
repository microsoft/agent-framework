# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

IMPORT_PATH = "agent_framework_orchestrations"
PACKAGE_NAME = "agent-framework-orchestrations"
_IMPORTS = [
    "__version__",
    # Sequential
    "SequentialBuilder",
    # Concurrent
    "ConcurrentBuilder",
    # Handoff
    "HandoffAgentExecutor",
    "HandoffAgentUserRequest",
    "HandoffBuilder",
    "HandoffConfiguration",
    "HandoffSentEvent",
    # Group Chat
    "AgentBasedGroupChatOrchestrator",
    "AgentOrchestrationOutput",
    "GroupChatBuilder",
    "GroupChatOrchestrator",
    "GroupChatSelectionFunction",
    "GroupChatState",
    # Magentic
    "MAGENTIC_MANAGER_NAME",
    "ORCH_MSG_KIND_INSTRUCTION",
    "ORCH_MSG_KIND_NOTICE",
    "ORCH_MSG_KIND_TASK_LEDGER",
    "ORCH_MSG_KIND_USER_TASK",
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
    "StandardMagenticManager",
]


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        try:
            return getattr(importlib.import_module(IMPORT_PATH), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_NAME}' package is not installed, please do `pip install {PACKAGE_NAME}`"
            ) from exc
    raise AttributeError(f"Module {IMPORT_PATH} has no attribute {name}.")


def __dir__() -> list[str]:
    return _IMPORTS
