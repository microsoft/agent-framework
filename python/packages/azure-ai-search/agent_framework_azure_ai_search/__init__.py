# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._context_provider import _AzureAISearchContextProvider
from ._search_provider import AzureAISearchContextProvider, AzureAISearchSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "_AzureAISearchContextProvider",
    "__version__",
]
