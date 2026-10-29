// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Stores cached values with their lifetimes and coordinates refreshes for each key.
/// </summary>
/// <remarks>
/// Expired entries remain available to refresh callbacks, which decide whether to replace them or return them unchanged.
/// Reads of the same key wait for earlier reads, then reuse the result only if it is still fresh.
/// </remarks>
internal sealed class McpCache<TKey, TValue>
    where TKey : notnull
{
    private readonly TimeProvider _timeProvider;
    private readonly ConcurrentDictionary<TKey, CacheState> _states;

    /// <summary>
    /// Initializes a new instance of the <see cref="McpCache{TKey, TValue}"/> class.
    /// </summary>
    public McpCache(TimeProvider timeProvider, IEqualityComparer<TKey> comparer)
    {
        this._timeProvider = Throw.IfNull(timeProvider);
        this._states = new(Throw.IfNull(comparer));
    }

    /// <summary>
    /// Returns a fresh cached value or invokes the callback to refresh it after earlier reads of the same key finish.
    /// </summary>
    /// <remarks>
    /// The callback receives the previous entry, including expired content, or null if nothing is cached.
    /// An optional condition requests a refresh even when the entry is fresh; it is checked after earlier reads finish.
    /// Returning the previous entry preserves its lifetime. Failed or canceled refreshes leave the cache unchanged.
    /// </remarks>
    public async ValueTask<TValue> GetOrRefreshAsync(
        TKey key,
        Func<McpCacheEntry<TValue>?, CancellationToken, ValueTask<McpCacheEntry<TValue>>> refresh,
        CancellationToken cancellationToken,
        Predicate<TValue>? needsRefresh = null)
    {
        _ = Throw.IfNull(refresh);

        CacheState state = this._states.GetOrAdd(key, static _ => new CacheState());

        // Later readers wait for this signal. Releasing it schedules their continuation.
        TaskCompletionSource<bool> completion = new(TaskCreationOptions.RunContinuationsAsynchronously);

        // Join the end of the queue and get the task to wait for in one atomic step.
        Task previous = Interlocked.Exchange(ref state.Tail, completion.Task);

        try
        {
            await previous.WaitAsync(cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();

            // The previous reader may have cached fresh content while this reader waited.
            var cached = Volatile.Read(ref state.Entry);
            if (cached?.Lifetime.IsFresh(this._timeProvider) == true && needsRefresh?.Invoke(cached.Value) != true)
            {
                return cached.Value;
            }

            var entry = await refresh(cached, cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();

            Volatile.Write(ref state.Entry, Throw.IfNull(entry));
            return entry.Value;
        }
        finally
        {
            // Release later readers even if this read fails or is canceled.
            _ = CompleteQueuedReadAsync(previous, completion);
        }
    }

    /// <summary>
    /// Returns whether a cached value matches the predicate, including when its entry has expired.
    /// </summary>
    public bool Contains(TKey key, Predicate<TValue> predicate)
    {
        _ = Throw.IfNull(predicate);

        return this._states.TryGetValue(key, out CacheState? state)
            && Volatile.Read(ref state.Entry) is { } entry
            && predicate(entry.Value);
    }

    /// <summary>
    /// Removes cached content without interrupting queued reads.
    /// </summary>
    public void Clear()
    {
        // Keep each queue in place so new readers cannot overtake readers already waiting.
        foreach (CacheState state in this._states.Values)
        {
            Volatile.Write(ref state.Entry, null);
        }
    }

    /// <summary>
    /// Releases the next reader without letting it skip an earlier read.
    /// </summary>
    private static async Task CompleteQueuedReadAsync(Task previous, TaskCompletionSource<bool> completion)
    {
        // A canceled waiter must not let later reads overtake its predecessor.
        // Queue tasks only signal completion; refresh failures stay with their caller.
        await previous.ConfigureAwait(false);
        completion.SetResult(true);
    }

    /// <summary>
    /// Holds a cached entry and the last queued read for one key.
    /// </summary>
    private sealed class CacheState
    {
        public McpCacheEntry<TValue>? Entry;
        public Task Tail = Task.CompletedTask;
    }
}

/// <summary>
/// Records when a response arrived and how long its value stays fresh.
/// </summary>
internal sealed class McpCacheLifetime
{
    private McpCacheLifetime()
    {
    }

    /// <summary>
    /// Creates a lifetime using the response timestamp and the resolved or server-provided TTL.
    /// </summary>
    public static McpCacheLifetime Create(long receivedTimestamp, TimeSpan? serverTimeToLive, Func<TimeSpan?, TimeSpan>? ttlResolver)
    {
        TimeSpan timeToLive = ttlResolver is null ? serverTimeToLive.GetValueOrDefault() : ttlResolver(serverTimeToLive);
        return new(receivedTimestamp, timeToLive > TimeSpan.Zero ? timeToLive : TimeSpan.Zero);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="McpCacheLifetime"/> class.
    /// </summary>
    public McpCacheLifetime(long receivedTimestamp, TimeSpan timeToLive)
    {
        this.ReceivedTimestamp = receivedTimestamp;
        this.TimeToLive = timeToLive;
    }

    /// <summary>
    /// Gets a lifetime that never expires.
    /// </summary>
    public static McpCacheLifetime Infinite { get; } = new();

    /// <summary>
    /// Gets the timestamp when the response arrived.
    /// </summary>
    public long ReceivedTimestamp { get; }

    /// <summary>
    /// Gets how long the value stays fresh after the response arrived.
    /// </summary>
    public TimeSpan TimeToLive { get; }

    /// <summary>
    /// Returns whether the lifetime has not expired, using the supplied clock.
    /// </summary>
    public bool IsFresh(TimeProvider timeProvider)
    {
        return ReferenceEquals(this, Infinite) || this.TimeToLive > timeProvider.GetElapsedTime(this.ReceivedTimestamp);
    }
}

/// <summary>
/// Pairs a cached value with its lifetime.
/// </summary>
internal sealed class McpCacheEntry<T>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="McpCacheEntry{T}"/> class.
    /// </summary>
    public McpCacheEntry(T value, McpCacheLifetime lifetime)
    {
        this.Value = value;
        this.Lifetime = Throw.IfNull(lifetime);
    }

    /// <summary>
    /// Gets the cached value.
    /// </summary>
    public T Value { get; }

    /// <summary>
    /// Gets the lifetime used to check whether the value is fresh.
    /// </summary>
    public McpCacheLifetime Lifetime { get; }
}
