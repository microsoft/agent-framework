# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import AnthropicChatOptions, AnthropicClient

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AnthropicChatOptions",
    "AnthropicClient",
    "__version__",
]
