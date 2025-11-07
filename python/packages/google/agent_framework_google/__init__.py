# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import GoogleAISettings

# NOTE: Client class will be imported here in a future PR

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "GoogleAISettings",
    "__version__",
]
