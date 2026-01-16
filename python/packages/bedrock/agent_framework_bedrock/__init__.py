# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import BedrockChatClient, BedrockChatOptions, BedrockGuardrailConfig, BedrockSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "BedrockChatClient",
    "BedrockChatOptions",
    "BedrockGuardrailConfig",
    "BedrockSettings",
    "__version__",
]
