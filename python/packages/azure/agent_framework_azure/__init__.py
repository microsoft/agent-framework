# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import AzureChatClient
from ._entra_id_authentication import get_entra_auth_token

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureChatClient",
    "__version__",
    "get_entra_auth_token",
]
