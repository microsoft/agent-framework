# Copyright (c) Microsoft. All rights reserved.

"""Valkey integration for Microsoft Agent Framework.

This module re-exports objects from:
- agent-framework-valkey

Supported classes:
- ValkeyContextProvider
- ValkeyChatMessageStore
"""

import importlib.metadata

from ._chat_message_store import ValkeyChatMessageStore
from ._context_provider import ValkeyContextProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "ValkeyChatMessageStore",
    "ValkeyContextProvider",
    "__version__",
]
