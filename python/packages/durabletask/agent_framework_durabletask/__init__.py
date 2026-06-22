# Copyright (c) Microsoft. All rights reserved.

"""Durable Task integration for Microsoft Agent Framework."""

import importlib.metadata

from ._async_bridge import run_agent_coroutine
from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._client import DurableAIAgentClient
from ._constants import (
    DEFAULT_MAX_POLL_RETRIES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    MIMETYPE_APPLICATION_JSON,
    MIMETYPE_TEXT_PLAIN,
    REQUEST_RESPONSE_FORMAT_JSON,
    REQUEST_RESPONSE_FORMAT_TEXT,
    THREAD_ID_FIELD,
    THREAD_ID_HEADER,
    WAIT_FOR_RESPONSE_FIELD,
    WAIT_FOR_RESPONSE_HEADER,
    ApiResponseFields,
    ContentTypes,
    DurableStateFields,
)
from ._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateContent,
    DurableAgentStateData,
    DurableAgentStateDataContent,
    DurableAgentStateEntry,
    DurableAgentStateEntryJsonType,
    DurableAgentStateErrorContent,
    DurableAgentStateFunctionCallContent,
    DurableAgentStateFunctionResultContent,
    DurableAgentStateHostedFileContent,
    DurableAgentStateHostedVectorStoreContent,
    DurableAgentStateMessage,
    DurableAgentStateRequest,
    DurableAgentStateResponse,
    DurableAgentStateTextContent,
    DurableAgentStateTextReasoningContent,
    DurableAgentStateUnknownContent,
    DurableAgentStateUriContent,
    DurableAgentStateUsage,
    DurableAgentStateUsageContent,
)
from ._entities import AgentEntity, AgentEntityStateProviderMixin
from ._executors import DurableAgentExecutor
from ._models import AgentSessionId, DurableAgentSession, RunRequest
from ._orchestration_context import DurableAIAgentOrchestrationContext
from ._response_utils import ensure_response_format, load_agent_response
from ._shim import DurableAIAgent
from ._worker import DurableAIAgentWorker
from ._workflows.activity import execute_workflow_activity
from ._workflows.client import DurableWorkflowClient
from ._workflows.context import WorkflowOrchestrationContext
from ._workflows.dt_context import DurableTaskWorkflowContext
from ._workflows.orchestrator import WORKFLOW_ORCHESTRATOR_NAME, run_workflow_orchestrator
from ._workflows.registration import WorkflowRegistrationPlan, plan_workflow_registration
from ._workflows.runner_context import CapturingRunnerContext
from ._workflows.serialization import deserialize_workflow_output

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "DEFAULT_MAX_POLL_RETRIES",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MIMETYPE_APPLICATION_JSON",
    "MIMETYPE_TEXT_PLAIN",
    "REQUEST_RESPONSE_FORMAT_JSON",
    "REQUEST_RESPONSE_FORMAT_TEXT",
    "THREAD_ID_FIELD",
    "THREAD_ID_HEADER",
    "WAIT_FOR_RESPONSE_FIELD",
    "WAIT_FOR_RESPONSE_HEADER",
    "WORKFLOW_ORCHESTRATOR_NAME",
    "AgentCallbackContext",
    "AgentEntity",
    "AgentEntityStateProviderMixin",
    "AgentResponseCallbackProtocol",
    "AgentSessionId",
    "ApiResponseFields",
    "CapturingRunnerContext",
    "ContentTypes",
    "DurableAIAgent",
    "DurableAIAgentClient",
    "DurableAIAgentOrchestrationContext",
    "DurableAIAgentWorker",
    "DurableAgentExecutor",
    "DurableAgentSession",
    "DurableAgentState",
    "DurableAgentStateContent",
    "DurableAgentStateData",
    "DurableAgentStateDataContent",
    "DurableAgentStateEntry",
    "DurableAgentStateEntryJsonType",
    "DurableAgentStateErrorContent",
    "DurableAgentStateFunctionCallContent",
    "DurableAgentStateFunctionResultContent",
    "DurableAgentStateHostedFileContent",
    "DurableAgentStateHostedVectorStoreContent",
    "DurableAgentStateMessage",
    "DurableAgentStateRequest",
    "DurableAgentStateResponse",
    "DurableAgentStateTextContent",
    "DurableAgentStateTextReasoningContent",
    "DurableAgentStateUnknownContent",
    "DurableAgentStateUriContent",
    "DurableAgentStateUsage",
    "DurableAgentStateUsageContent",
    "DurableStateFields",
    "DurableTaskWorkflowContext",
    "DurableWorkflowClient",
    "RunRequest",
    "WorkflowOrchestrationContext",
    "WorkflowRegistrationPlan",
    "__version__",
    "deserialize_workflow_output",
    "ensure_response_format",
    "execute_workflow_activity",
    "load_agent_response",
    "plan_workflow_registration",
    "run_agent_coroutine",
    "run_workflow_orchestrator",
]
