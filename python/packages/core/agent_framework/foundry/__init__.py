# Copyright (c) Microsoft. All rights reserved.

"""Foundry integration namespace for optional Agent Framework connectors.

This module lazily re-exports objects from cloud Foundry and Foundry Local connector packages.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "FoundryAgent": ("agent_framework_foundry", "agent-framework-foundry"),
    "FoundryChatClient": ("agent_framework_foundry", "agent-framework-foundry"),
    "FoundryChatOptions": ("agent_framework_foundry", "agent-framework-foundry"),
    "FoundryMemoryProvider": ("agent_framework_foundry", "agent-framework-foundry"),
    "FoundryLocalChatOptions": ("agent_framework_foundry_local", "agent-framework-foundry-local"),
    "FoundryLocalClient": ("agent_framework_foundry_local", "agent-framework-foundry-local"),
    "FoundryLocalSettings": ("agent_framework_foundry_local", "agent-framework-foundry-local"),
    "RawFoundryAgent": ("agent_framework_foundry", "agent-framework-foundry"),
    "RawFoundryAgentChatClient": ("agent_framework_foundry", "agent-framework-foundry"),
    "RawFoundryChatClient": ("agent_framework_foundry", "agent-framework-foundry"),
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
    raise AttributeError(f"Module `foundry` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
