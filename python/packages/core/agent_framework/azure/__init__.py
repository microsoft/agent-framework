# Copyright (c) Microsoft. All rights reserved.


import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AgentCallbackContext": ("agent_framework_azurefunctions", "azurefunctions"),
    "AgentFunctionApp": ("agent_framework_azurefunctions", "azurefunctions"),
    "AgentResponseCallbackProtocol": ("agent_framework_azurefunctions", "azurefunctions"),
    "AzureAIAgentClient": ("agent_framework_azure_ai", "azure-ai"),
    "AzureAIClient": ("agent_framework_azure_ai", "azure-ai"),
    "AzureOpenAIAssistantsClient": ("agent_framework.azure._assistants_client", "core"),
    "AzureOpenAIChatClient": ("agent_framework.azure._chat_client", "core"),
    "AzureAISettings": ("agent_framework_azure_ai", "azure-ai"),
    "AzureOpenAISettings": ("agent_framework.azure._shared", "core"),
    "AzureOpenAIResponsesClient": ("agent_framework.azure._responses_client", "core"),
    "DurableAIAgent": ("agent_framework_azurefunctions", "azurefunctions"),
    "get_entra_auth_token": ("agent_framework.azure._entra_id_authentication", "core"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        package_name, package_extra = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(package_name), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"please use `pip install agent-framework-{package_extra}`, "
                "or update your requirements.txt or pyproject.toml file."
            ) from exc
    raise AttributeError(f"Module `azure` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
