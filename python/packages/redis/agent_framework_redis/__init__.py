# Copyright (c) Microsoft. All rights reserved.
import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

from ._redis_memory import (
    RedisMemory,
    RedisMemoryConfig,
)

__all__ = ["RedisMemory", "RedisMemoryConfig", "__version__"]
