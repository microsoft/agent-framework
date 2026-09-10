# Copyright (c) Microsoft. All rights reserved.

# Type stubs for the agent_framework.azure lazy-loading namespace.
# Install the relevant packages for full type support.

from agent_framework_azure_ai_search import (
    AzureAISearchCollection,
    AzureAISearchContextProvider,
    AzureAISearchSettings,
    AzureAISearchStore,
)
from agent_framework_azure_cosmos import CosmosHistoryProvider
from agent_framework_azurefunctions import AgentFunctionApp, WorkflowHitlContext
from agent_framework_durabletask import (
    AgentCallbackContext,
    AgentResponseCallbackProtocol,
    DurableAIAgent,
    DurableAIAgentClient,
    DurableAIAgentOrchestrationContext,
    DurableAIAgentWorker,
    DurableWorkflowClient,
)

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "AzureAISearchCollection",
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "AzureAISearchStore",
    "CosmosHistoryProvider",
    "DurableAIAgent",
    "DurableAIAgentClient",
    "DurableAIAgentOrchestrationContext",
    "DurableAIAgentWorker",
    "DurableWorkflowClient",
    "WorkflowHitlContext",
]
