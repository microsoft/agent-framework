# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import GeminiChatClient, GeminiChatOptions, GeminiSettings, RawGeminiChatClient, ThinkingConfig

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "GeminiChatClient",
    "GeminiChatOptions",
    "GeminiSettings",
    "RawGeminiChatClient",
    "ThinkingConfig",
    "__version__",
]
