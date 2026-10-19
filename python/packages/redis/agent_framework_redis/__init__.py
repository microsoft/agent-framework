# Copyright (c) Microsoft. All rights reserved.

"""Redis history, context providers, and experimental vector collections."""

import importlib.metadata

from ._context_provider import RedisContextProvider
from ._history_provider import RedisHistoryProvider
from ._vector_store import RedisCollection, RedisSettings, RedisStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "RedisCollection",
    "RedisContextProvider",
    "RedisHistoryProvider",
    "RedisSettings",
    "RedisStore",
    "__version__",
]
