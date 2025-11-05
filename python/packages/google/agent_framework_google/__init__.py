# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

# NOTE: Client classes will be imported here in PR #2 and PR #4
# from ._chat_client import GoogleAIChatClient, VertexAIChatClient

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    # "GoogleAIChatClient",  # Will be added in PR #2
    # "VertexAIChatClient",  # Will be added in PR #4
    "__version__",
]
