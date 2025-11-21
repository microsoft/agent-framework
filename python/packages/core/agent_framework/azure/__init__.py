# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AgentCallbackContext": ("agent_framework_azurefunctions", "agent-framework-azurefunctions"),
    "AgentFunctionApp": ("agent_framework_azurefunctions", "agent-framework-azurefunctions"),
    "AgentResponseCallbackProtocol": ("agent_framework_azurefunctions", "agent-framework-azurefunctions"),
    "AzureAIAgentClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAIClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureAISearchContextProvider": ("agent_framework_azure_ai_search", "agent-framework-azure-ai-search"),
    "AzureAISearchSettings": ("agent_framework_azure_ai_search", "agent-framework-azure-ai-search"),
    "AzureAISettings": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
    "AzureOpenAIAssistantsClient": ("agent_framework.azure._assistants_client", "agent-framework-core"),
    "AzureOpenAIChatClient": ("agent_framework.azure._chat_client", "agent-framework-core"),
    "AzureOpenAIResponsesClient": ("agent_framework.azure._responses_client", "agent-framework-core"),
    "AzureOpenAISettings": ("agent_framework.azure._shared", "agent-framework-core"),
    "DurableAIAgent": ("agent_framework_azurefunctions", "agent-framework-azurefunctions"),
    "get_entra_auth_token": ("agent_framework.azure._entra_id_authentication", "agent-framework-core"),
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
