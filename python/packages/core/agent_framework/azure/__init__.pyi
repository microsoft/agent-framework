# Copyright (c) Microsoft. All rights reserved.

# Type stubs for the agent_framework.azure lazy-loading namespace.
# Install the relevant packages for full type support.

from agent_framework_azure_ai import (
    AzureAISettings,
    AzureCredentialTypes,
    AzureTokenProvider,
)
from agent_framework_azure_ai_search import (
    AzureAISearchContextProvider,
    AzureAISearchSettings,
)
from agent_framework_azurefunctions import AgentFunctionApp
from agent_framework_durabletask import (
    AgentCallbackContext,
    AgentResponseCallbackProtocol,
    DurableAIAgent,
    DurableAIAgentClient,
    DurableAIAgentOrchestrationContext,
    DurableAIAgentWorker,
)

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "AzureAISettings",
    "AzureCredentialTypes",
    "AzureTokenProvider",
    "DurableAIAgent",
    "DurableAIAgentClient",
    "DurableAIAgentOrchestrationContext",
    "DurableAIAgentWorker",
]
