# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._context_provider import (
    PREVIEW_API_VERSION,
    STABLE_API_VERSION,
    AzureAISearchContextProvider,
    AzureAISearchSettings,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "PREVIEW_API_VERSION",
    "STABLE_API_VERSION",
    "AzureAISearchContextProvider",
    "AzureAISearchSettings",
    "__version__",
]
