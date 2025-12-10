# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview cache provider."""

import asyncio

from agent_framework_purview._cache import (
    InMemoryCacheProvider,
    create_protection_scopes_cache_key,
)
from agent_framework_purview._models import PolicyLocation, ProtectionScopesRequest


class TestInMemoryCacheProvider:
    """Test InMemoryCacheProvider functionality."""

    async def test_cache_set_and_get(self) -> None:
        """Test basic set and get operations."""
        cache = InMemoryCacheProvider()

        await cache.set("key1", "value1")
        result = await cache.get("key1")

        assert result == "value1"

    async def test_cache_get_nonexistent_key(self) -> None:
        """Test get returns None for non-existent key."""
        cache = InMemoryCacheProvider()

        result = await cache.get("nonexistent")

        assert result is None

    async def test_cache_expiration(self) -> None:
        """Test that cached values expire after TTL."""
        cache = InMemoryCacheProvider(default_ttl_seconds=1)

        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

        await asyncio.sleep(1.1)
        result = await cache.get("key1")
        assert result is None

    async def test_cache_custom_ttl(self) -> None:
        """Test that custom TTL overrides default."""
        cache = InMemoryCacheProvider(default_ttl_seconds=10)

        await cache.set("key1", "value1", ttl_seconds=1)
        result = await cache.get("key1")
        assert result == "value1"

        await asyncio.sleep(1.1)
        result = await cache.get("key1")
        assert result is None

    async def test_cache_update_existing_key(self) -> None:
        """Test updating an existing cache entry."""
        cache = InMemoryCacheProvider()

        await cache.set("key1", "value1")
        await cache.set("key1", "value2")
        result = await cache.get("key1")

        assert result == "value2"

    async def test_cache_remove(self) -> None:
        """Test removing a cache entry."""
        cache = InMemoryCacheProvider()

        await cache.set("key1", "value1")
        await cache.remove("key1")
        result = await cache.get("key1")

        assert result is None

    async def test_cache_remove_nonexistent_key(self) -> None:
        """Test removing non-existent key does not raise error."""
        cache = InMemoryCacheProvider()

        await cache.remove("nonexistent")

    async def test_cache_size_limit_eviction(self) -> None:
        """Test that cache evicts old entries when size limit is reached."""
        cache = InMemoryCacheProvider(max_size_bytes=200)

        await cache.set("key1", "a" * 50)
        await cache.set("key2", "b" * 50)
        await cache.set("key3", "c" * 50)

        await cache.set("key4", "d" * 100)

        result1 = await cache.get("key1")
        assert result1 is None

    async def test_estimate_size_with_pydantic_model(self) -> None:
        """Test size estimation with Pydantic models."""
        cache = InMemoryCacheProvider()

        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        request = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location])

        await cache.set("key1", request)
        result = await cache.get("key1")

        assert result == request

    async def test_estimate_size_fallback(self) -> None:
        """Test size estimation fallback for non-serializable objects."""
        cache = InMemoryCacheProvider()

        class CustomObject:
            pass

        obj = CustomObject()
        await cache.set("key1", obj)
        result = await cache.get("key1")

        assert result == obj

    async def test_cache_multiple_updates(self) -> None:
        """Test that updating a key multiple times maintains correct size tracking."""
        cache = InMemoryCacheProvider(max_size_bytes=1000)

        await cache.set("key1", "a" * 100)
        initial_size = cache._current_size_bytes

        await cache.set("key1", "b" * 200)

        assert cache._current_size_bytes != initial_size

    async def test_eviction_with_stale_heap_entries(self) -> None:
        """Test that eviction correctly handles stale heap entries."""
        cache = InMemoryCacheProvider(max_size_bytes=500)

        await cache.set("key1", "a" * 100, ttl_seconds=10)
        await cache.set("key2", "b" * 100, ttl_seconds=10)
        await cache.set("key1", "c" * 100, ttl_seconds=20)

        await cache.set("key3", "d" * 300)

        result = await cache.get("key1")
        assert result is not None


class TestCreateProtectionScopesCacheKey:
    """Test cache key generation for ProtectionScopesRequest."""

    def test_cache_key_deterministic(self) -> None:
        """Test that same request generates same cache key."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        request1 = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location])
        request2 = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location])

        key1 = create_protection_scopes_cache_key(request1)
        key2 = create_protection_scopes_cache_key(request2)

        assert key1 == key2

    def test_cache_key_different_for_different_requests(self) -> None:
        """Test that different requests generate different cache keys."""
        location1 = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id1"})
        location2 = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id2"})
        request1 = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location1])
        request2 = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location2])

        key1 = create_protection_scopes_cache_key(request1)
        key2 = create_protection_scopes_cache_key(request2)

        assert key1 != key2

    def test_cache_key_excludes_correlation_id(self) -> None:
        """Test that correlation_id is excluded from cache key."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        request1 = ProtectionScopesRequest(
            user_id="user1", tenant_id="tenant1", locations=[location], correlation_id="corr1"
        )
        request2 = ProtectionScopesRequest(
            user_id="user1", tenant_id="tenant1", locations=[location], correlation_id="corr2"
        )

        key1 = create_protection_scopes_cache_key(request1)
        key2 = create_protection_scopes_cache_key(request2)

        assert key1 == key2

    def test_cache_key_format(self) -> None:
        """Test that cache key has expected format."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        request = ProtectionScopesRequest(user_id="user1", tenant_id="tenant1", locations=[location])

        key = create_protection_scopes_cache_key(request)

        assert key.startswith("purview:protection_scopes:")
        assert len(key) > len("purview:protection_scopes:")
