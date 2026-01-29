# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

# Maps export names to (module_path, package_name)
_IMPORTS: dict[str, tuple[str, str]] = {
    # From agent-framework-anthropic
    "__version__": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "AnthropicClient": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "AnthropicChatOptions": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "AnthropicSettings": ("agent_framework_anthropic", "agent-framework-anthropic"),
    # From agent-framework-claude
    "ClaudeAgent": ("agent_framework_claude", "agent-framework-claude"),
    "ClaudeAgentOptions": ("agent_framework_claude", "agent-framework-claude"),
    "ClaudeAgentSettings": ("agent_framework_claude", "agent-framework-claude"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        module_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(module_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{package_name}' package is not installed, please do `pip install {package_name}`"
            ) from exc
    raise AttributeError(f"Module 'agent_framework.anthropic' has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
