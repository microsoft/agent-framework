# Copyright (c) Microsoft. All rights reserved.

# Type stubs for the agent_framework.azure lazy-loading namespace.
# Install the relevant packages for full type support.

from agent_framework_azure_ai import (
    AzureAIAgentClient,
    AzureAIAgentsProvider,
    AzureAIClient,
    AzureAIProjectAgentOptions,
    AzureAIProjectAgentProvider,
    AzureAISettings,
    AzureCredentialTypes,
    AzureOpenAIAssistantsClient,
    AzureOpenAIAssistantsOptions,
    AzureOpenAIChatClient,
    AzureOpenAIChatOptions,
    AzureOpenAIEmbeddingClient,
    AzureOpenAIResponsesClient,
    AzureOpenAIResponsesOptions,
    AzureOpenAISettings,
    AzureTokenProvider,
    AzureUserSecurityContext,
    RawAzureAIClient,
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
    "AzureAIAgentClient",
    "AzureAIAgentsProvider",
    "AzureAIClient",
    "AzureAIProjectAgentOptions",
    "AzureAIProjectAgentProvider",
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "AzureAISettings",
    "AzureCredentialTypes",
    "AzureOpenAIAssistantsClient",
    "AzureOpenAIAssistantsOptions",
    "AzureOpenAIChatClient",
    "AzureOpenAIChatOptions",
    "AzureOpenAIEmbeddingClient",
    "AzureOpenAIResponsesClient",
    "AzureOpenAIResponsesOptions",
    "AzureOpenAISettings",
    "AzureTokenProvider",
    "AzureUserSecurityContext",
    "DurableAIAgent",
    "DurableAIAgentClient",
    "DurableAIAgentOrchestrationContext",
    "DurableAIAgentWorker",
    "RawAzureAIClient",
]
