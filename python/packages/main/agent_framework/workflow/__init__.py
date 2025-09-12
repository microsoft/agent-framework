# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

PACKAGE_NAME = "agent_framework_workflow"
PACKAGE_EXTRA = "workflow"
_IMPORTS = [
    "Executor",
    "FunctionExecutor",
    "executor",
    "WorkflowContext",
    "__version__",
    "events",
    "WorkflowBuilder",
    "ExecutorCompletedEvent",
    "ExecutorEvent",
    "ExecutorInvokeEvent",
    "RequestInfoEvent",
    "WorkflowCompletedEvent",
    "WorkflowEvent",
    "WorkflowStartedEvent",
    "AgentRunEvent",
    "AgentRunUpdateEvent",
    "handler",
    "AgentExecutor",
    "MagenticAgentDeltaEvent",
    "MagenticCallbackEvent",
    "MagenticCallbackMode",
    "MagenticAgentMessageEvent",
    "MagenticFinalResultEvent",
    "MagenticManagerBase",
    "MagenticOrchestratorMessageEvent",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "RequestInfoExecutor",
    "RequestInfoMessage",
    "WorkflowRunResult",
    "Workflow",
    "WorkflowAgent",
    "WorkflowViz",
    "FileCheckpointStorage",
    "InMemoryCheckpointStorage",
    "CheckpointStorage",
    "WorkflowCheckpoint",
    "Case",
    "Default",
    "RequestResponse",
    "SubWorkflowRequestInfo",
    "SubWorkflowResponse",
    "WorkflowExecutor",
    "intercepts_request",
    "MagenticBuilder",
    "PlanReviewDecision",
    "PlanReviewReply",
    "PlanReviewRequest",
    "RequestInfoEvent",
    "StandardMagenticManager",
    "ConcurrentBuilder",
]


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        try:
            return getattr(importlib.import_module(PACKAGE_NAME), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_EXTRA}' extra is not installed, "
                f"please do `pip install agent-framework[{PACKAGE_EXTRA}]`"
            ) from exc
    raise AttributeError(f"Module {PACKAGE_NAME} has no attribute {name}.")


def __dir__() -> list[str]:
    return _IMPORTS
