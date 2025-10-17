# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import AzureAIAgentClient, AzureAISettings
from ._search_provider import AzureAISearchContextProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureAIAgentClient",
    "AzureAISearchContextProvider",
    "AzureAISettings",
    "__version__",
]
