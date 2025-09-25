# Copyright (c) Microsoft. All rights reserved.


import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, list[str]]] = {
    "AzureAIAgentClient": ("agent_framework_azure_ai", ["azure_ai", "azure"]),
    "AzureOpenAIAssistantsClient": ("agent_framework.azure._assistants_client", []),
    "AzureOpenAIChatClient": ("agent_framework.azure._chat_client", []),
    "AzureAISettings": ("agent_framework_azure_ai", ["azure_ai", "azure"]),
    "AzureOpenAISettings": ("agent_framework.azure._shared", []),
    "AzureOpenAIResponsesClient": ("agent_framework.azure._responses_client", []),
    "get_entra_auth_token": ("agent_framework.azure._entra_id_authentication", []),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        package_name, package_extra = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(package_name), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The {' or '.join(package_extra)} extra is not installed, "
                f"please use `pip install agent-framework[{package_extra[0]}]`, "
                "or update your requirements.txt or pyproject.toml file."
            ) from exc
    raise AttributeError(f"Module `azure` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
