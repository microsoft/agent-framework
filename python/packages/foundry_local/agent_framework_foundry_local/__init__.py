# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._foundry_local_client import FoundryLocalChatOptions, FoundryLocalClient, FoundryLocalSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
    "__version__",
]
