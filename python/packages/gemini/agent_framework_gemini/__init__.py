# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import (
    GeminiChatClient,
    GeminiChatOptions,
    GoogleGeminiSettings,
    RawGeminiChatClient,
    ThinkingConfig,
)
from ._embedding_client import (
    GeminiEmbeddingClient,
    GeminiEmbeddingOptions,
    RawGeminiEmbeddingClient,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "GeminiChatClient",
    "GeminiChatOptions",
    "GeminiEmbeddingClient",
    "GeminiEmbeddingOptions",
    "GoogleGeminiSettings",
    "RawGeminiChatClient",
    "RawGeminiEmbeddingClient",
    "ThinkingConfig",
    "__version__",
]
