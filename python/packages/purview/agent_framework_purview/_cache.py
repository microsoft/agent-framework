# Copyright (c) Microsoft. All rights reserved.
"""Cache provider for Purview data."""

from __future__ import annotations

import hashlib
import heapq
import json
import sys
import time
from typing import Any, Protocol

from ._models import ProtectionScopesRequest


class CacheProvider(Protocol):
    """Protocol for cache providers used by Purview integration."""

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found or expired.
        """
        ...

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl_seconds: Time to live in seconds. If None, uses provider default.
        """
        ...

    async def remove(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key.
        """
        ...


class InMemoryCacheProvider:
    """Simple in-memory cache implementation for Purview data.

    This implementation uses a dictionary with expiration tracking and size limits.
    """

    def __init__(self, default_ttl_seconds: int = 1800, max_size_bytes: int = 200 * 1024 * 1024):
        """Initialize the in-memory cache.

        Args:
            default_ttl_seconds: Default time to live in seconds (default 1800 = 30 minutes).
            max_size_bytes: Maximum cache size in bytes (default 200MB).
        """
        self._cache: dict[str, tuple[Any, float, int]] = {}  # key -> (value, expiry, size)
        self._expiry_heap: list[tuple[float, str]] = []  # min-heap of (expiry_time, key)
        self._default_ttl = default_ttl_seconds
        self._max_size_bytes = max_size_bytes
        self._current_size_bytes = 0

    def _estimate_size(self, value: Any) -> int:
        """Estimate the size of a cached value in bytes.

        Args:
            value: The value to estimate size for.

        Returns:
            Estimated size in bytes.
        """
        try:
            if hasattr(value, "model_dump_json"):
                return len(value.model_dump_json().encode("utf-8"))

            return len(json.dumps(value, default=str).encode("utf-8"))
        except Exception:
            # Fallback to sys.getsizeof if JSON serialization fails
            try:
                return sys.getsizeof(value)
            except Exception:
                # Conservative fallback estimate
                return 1024

    def _evict_if_needed(self, required_size: int) -> None:
        """Evict oldest entries if needed to make room for new entry.

        Uses a min-heap to efficiently find and evict entries with earliest expiry times.
        Also cleans up stale heap entries for keys that no longer exist in cache.

        Args:
            required_size: Size in bytes needed for new entry.
        """
        if self._current_size_bytes + required_size <= self._max_size_bytes:
            return

        while self._expiry_heap and self._current_size_bytes + required_size > self._max_size_bytes:
            expiry_time, key = heapq.heappop(self._expiry_heap)

            if key in self._cache:
                _, cached_expiry, size = self._cache[key]
                if cached_expiry == expiry_time:
                    del self._cache[key]
                    self._current_size_bytes -= size
                # else: stale heap entry, already updated/removed, skip it

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found or expired.
        """
        if key not in self._cache:
            return None

        value, expiry, size = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            self._current_size_bytes -= size
            return None

        return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl_seconds: Time to live in seconds. If None, uses default TTL.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expiry = time.time() + ttl
        size = self._estimate_size(value)

        # Remove old entry if exists
        if key in self._cache:
            old_size = self._cache[key][2]
            self._current_size_bytes -= old_size

        # Evict if needed
        self._evict_if_needed(size)

        self._cache[key] = (value, expiry, size)
        self._current_size_bytes += size

        heapq.heappush(self._expiry_heap, (expiry, key))

    async def remove(self, key: str) -> None:
        """Remove a value from the cache.

        Args:
            key: The cache key.
        """
        entry = self._cache.pop(key, None)
        if entry is not None:
            self._current_size_bytes -= entry[2]
        self._cache.pop(key, None)


def create_protection_scopes_cache_key(request: ProtectionScopesRequest) -> str:
    """Create a cache key for a ProtectionScopesRequest.

    The key is based on the serialized request content (excluding correlation_id).

    Args:
        request: The protection scopes request.

    Returns:
        A string cache key.
    """
    data = request.to_dict(exclude_none=True)

    for field in ["correlation_id"]:
        data.pop(field, None)

    json_str = json.dumps(data, sort_keys=True)
    return f"purview:protection_scopes:{hashlib.sha256(json_str.encode()).hexdigest()}"


__all__ = [
    "CacheProvider",
]
