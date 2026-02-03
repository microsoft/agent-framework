# Copyright (c) Microsoft. All rights reserved.

from agent_framework_azure_ai import (
    AzureAIAgentClient,
    AzureAIAgentsProvider,
    AzureAIClient,
    AzureAIProjectAgentOptions,
    AzureAIProjectAgentProvider,
    AzureAISettings,
)
from agent_framework_azure_ai_search import AzureAISearchContextProvider, AzureAISearchSettings
from agent_framework_azurefunctions import AgentFunctionApp
from agent_framework_durabletask import (
    AgentCallbackContext,
    AgentResponseCallbackProtocol,
    DurableAIAgent,
    DurableAIAgentClient,
    DurableAIAgentOrchestrationContext,
    DurableAIAgentWorker,
)

from agent_framework.azure._assistants_client import AzureOpenAIAssistantsClient
from agent_framework.azure._chat_client import AzureOpenAIChatClient
from agent_framework.azure._entra_id_authentication import get_entra_auth_token
from agent_framework.azure._responses_client import AzureOpenAIResponsesClient
from agent_framework.azure._shared import AzureOpenAISettings

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
    "AzureOpenAIAssistantsClient",
    "AzureOpenAIChatClient",
    "AzureOpenAIResponsesClient",
    "AzureOpenAISettings",
    "DurableAIAgent",
    "DurableAIAgentClient",
    "DurableAIAgentOrchestrationContext",
    "DurableAIAgentWorker",
    "get_entra_auth_token",
]
