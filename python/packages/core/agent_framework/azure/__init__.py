# Copyright (c) Microsoft. All rights reserved.

"""Azure integration namespace for optional Agent Framework connectors.

This module lazily re-exports objects from optional Azure connector packages.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AgentCallbackContext": ("agent_framework_durabletask", "agent-framework-durabletask"),
    "AgentFunctionApp": ("agent_framework_azurefunctions", "agent-framework-azurefunctions"),
    "AgentResponseCallbackProtocol": ("agent_framework_durabletask", "agent-framework-durabletask"),
    "AzureAIAgentClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIAgentOptions": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIProjectAgentOptions": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIProjectAgentProvider": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAISearchContextProvider": ("agent_framework_azure_ai_search", "agent-framework-azure-ai-search"),
    "AzureAISearchSettings": ("agent_framework_azure_ai_search", "agent-framework-azure-ai-search"),
    "AzureAISettings": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIAgentsProvider": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureCredentialTypes": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureTokenProvider": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIAssistantsClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIAssistantsOptions": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIChatClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIChatOptions": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIEmbeddingClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIResponsesClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIResponsesOptions": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAISettings": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureUserSecurityContext": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "DurableAIAgent": ("agent_framework_durabletask", "agent-framework-durabletask"),
    "DurableAIAgentClient": ("agent_framework_durabletask", "agent-framework-durabletask"),
    "DurableAIAgentOrchestrationContext": ("agent_framework_durabletask", "agent-framework-durabletask"),
    "DurableAIAgentWorker": ("agent_framework_durabletask", "agent-framework-durabletask"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The package {package_name} is required to use `{name}`. "
                f"Please use `pip install {package_name}`, or update your requirements.txt or pyproject.toml file."
            ) from exc
    raise AttributeError(f"Module `azure` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
