# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock integration namespace for optional Agent Framework connectors.

This module lazily re-exports objects from:
- ``agent-framework-bedrock``

Supported classes:
- BedrockChatClient
- BedrockChatOptions
- BedrockEmbeddingClient
- BedrockEmbeddingOptions
- BedrockEmbeddingSettings
- BedrockGuardrailConfig
- BedrockSettings
"""

import importlib
from typing import Any

IMPORT_PATH = "agent_framework_bedrock"
PACKAGE_NAME = "agent-framework-bedrock"
_IMPORTS = [
    "BedrockChatClient",
    "BedrockChatOptions",
    "BedrockEmbeddingClient",
    "BedrockEmbeddingOptions",
    "BedrockEmbeddingSettings",
    "BedrockGuardrailConfig",
    "BedrockSettings",
]


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        try:
            return getattr(importlib.import_module(IMPORT_PATH), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_NAME}' package is not installed, please do `pip install {PACKAGE_NAME}`"
            ) from exc
    raise AttributeError(f"Module {IMPORT_PATH} has no attribute {name}.")


def __dir__() -> list[str]:
    return _IMPORTS
