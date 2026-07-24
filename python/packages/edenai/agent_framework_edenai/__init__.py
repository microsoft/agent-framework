# Copyright (c) Microsoft. All rights reserved.

"""Eden AI integration for Microsoft Agent Framework.

Eden AI is a gateway that exposes many model providers behind a single
OpenAI compatible API and one key.
"""

import importlib.metadata

from ._chat_client import EdenAIChatClient, EdenAIChatOptions, EdenAISettings

try:
    __version__ = importlib.metadata.version("agent-framework-edenai")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "EdenAIChatClient",
    "EdenAIChatOptions",
    "EdenAISettings",
    "__version__",
]
