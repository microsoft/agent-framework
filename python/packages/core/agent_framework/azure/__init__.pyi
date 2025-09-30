# Copyright (c) Microsoft. All rights reserved.

from agent_framework_azure_ai import AzureAIAgentClient, AzureAISettings

from agent_framework.azure._assistants_client import AzureOpenAIAssistantsClient
from agent_framework.azure._chat_client import AzureOpenAIChatClient
from agent_framework.azure._entra_id_authentication import get_entra_auth_token
from agent_framework.azure._responses_client import AzureOpenAIResponsesClient
from agent_framework.azure._shared import AzureOpenAISettings

__all__ = [
    "AzureAIAgentClient",
    "AzureAISettings",
    "AzureOpenAIAssistantsClient",
    "AzureOpenAIChatClient",
    "AzureOpenAIResponsesClient",
    "AzureOpenAISettings",
    "get_entra_auth_token",
]
