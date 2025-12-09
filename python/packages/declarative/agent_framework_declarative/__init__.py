# Copyright (c) Microsoft. All rights reserved.

from importlib import metadata

from ._loader import AgentFactory, DeclarativeLoaderError, ProviderLookupError, ProviderTypeMapping

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = ["AgentFactory", "DeclarativeLoaderError", "ProviderLookupError", "ProviderTypeMapping", "__version__"]
