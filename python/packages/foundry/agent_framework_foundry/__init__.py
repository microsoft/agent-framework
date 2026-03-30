# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import FoundryAgent, RawFoundryAgent, RawFoundryAgentChatClient
from ._chat_client import FoundryChatClient, FoundryChatOptions, RawFoundryChatClient
from ._memory_provider import FoundryMemoryProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "FoundryAgent",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryMemoryProvider",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "__version__",
]
