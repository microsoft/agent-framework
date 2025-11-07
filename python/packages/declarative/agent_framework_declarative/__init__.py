# Copyright (c) Microsoft. All rights reserved.

import importlib

from ._loader import AgentFactory, DeclarativeLoaderError, ProviderLookupError

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = ["AgentFactory", "DeclarativeLoaderError", "ProviderLookupError", "__version__"]
