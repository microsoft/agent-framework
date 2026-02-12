# Copyright (c) Microsoft. All rights reserved.
import importlib.metadata

from ._chat_message_store import RedisChatMessageStore
from ._context_provider import _RedisContextProvider
from ._history_provider import _RedisHistoryProvider
from ._provider import RedisProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "RedisChatMessageStore",
    "RedisProvider",
    "_RedisContextProvider",
    "_RedisHistoryProvider",
    "__version__",
]
