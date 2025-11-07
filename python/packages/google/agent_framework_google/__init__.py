# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

# NOTE: Client class will be imported here in a future PR
# from ._chat_client import GoogleAIChatClient

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    # "GoogleAIChatClient",  # Will be added in a future PR
    "__version__",
]
