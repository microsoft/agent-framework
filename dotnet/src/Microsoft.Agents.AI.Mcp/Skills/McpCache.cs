// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Stores cached values and checks whether they have expired.
/// </summary>
/// <remarks>
/// Expired entries remain available. Callers decide when to fetch or replace values.
/// </remarks>
internal sealed class McpCache<TKey, TValue>
    where TKey : notnull
{
    private readonly TimeProvider _timeProvider;
    private readonly ConcurrentDictionary<TKey, McpCacheEntry<TValue>> _entries;

    /// <summary>
    /// Initializes a new instance of the <see cref="McpCache{TKey, TValue}"/> class.
    /// </summary>
    public McpCache(TimeProvider timeProvider, IEqualityComparer<TKey> comparer)
    {
        this._timeProvider = Throw.IfNull(timeProvider);
        this._entries = new(Throw.IfNull(comparer));
    }

    /// <summary>
    /// Gets an entry, including expired entries, or returns null if the key is not cached.
    /// </summary>
    public McpCacheEntry<TValue>? Get(TKey key)
    {
        this._entries.TryGetValue(key, out var entry);
        return entry;
    }

    /// <summary>
    /// Returns whether an entry is still within its lifetime without extending it.
    /// </summary>
    public bool IsFresh(McpCacheEntry<TValue> entry)
    {
        return entry.Lifetime.TimeToLive > this._timeProvider.GetElapsedTime(entry.Lifetime.ReceivedTimestamp);
    }

    /// <summary>
    /// Stores or replaces a value and its lifetime together.
    /// </summary>
    public void Set(TKey key, McpCacheEntry<TValue> entry)
    {
        this._entries[key] = Throw.IfNull(entry);
    }

    /// <summary>
    /// Removes all stored entries.
    /// </summary>
    public void Clear() => this._entries.Clear();
}

/// <summary>
/// Records when a response arrived and how long its value stays fresh.
/// </summary>
internal readonly record struct McpCacheLifetime(long ReceivedTimestamp, TimeSpan TimeToLive);

/// <summary>
/// Pairs a cached value with its lifetime.
/// </summary>
internal sealed record McpCacheEntry<T>(T Value, McpCacheLifetime Lifetime);
