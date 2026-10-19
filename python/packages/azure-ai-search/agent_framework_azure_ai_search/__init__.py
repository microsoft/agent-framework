# Copyright (c) Microsoft. All rights reserved.

"""Azure AI Search context providers and vector stores."""

import importlib.metadata

from ._context_provider import AzureAISearchContextProvider, AzureAISearchSettings
from ._vector_store import AzureAISearchCollection, AzureAISearchStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureAISearchCollection",
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "AzureAISearchStore",
    "__version__",
]
