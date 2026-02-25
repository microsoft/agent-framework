# Copyright (c) Microsoft. All rights reserved.

"""Anthropic integration namespace for optional Agent Framework connectors.

This module lazily re-exports objects from:
- ``agent-framework-anthropic``
- ``agent-framework-claude``

Supported classes:
- AnthropicClient
- AnthropicChatOptions
- ClaudeAgent
- ClaudeAgentOptions
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AnthropicClient": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "AnthropicChatOptions": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "ClaudeAgent": ("agent_framework_claude", "agent-framework-claude"),
    "ClaudeAgentOptions": ("agent_framework_claude", "agent-framework-claude"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{package_name}' package is not installed, please do `pip install {package_name}`"
            ) from exc
    raise AttributeError(f"Module `anthropic` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
