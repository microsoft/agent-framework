// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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
/// Keys without cached content are removed after their pending reads finish.
/// Optional limits restrict the number and combined size of cached entries, including expired entries.
/// </remarks>
[SuppressMessage("Design", "CA1001:Types that own disposable fields should be disposable", Justification = "The private semaphore's AvailableWaitHandle is never accessed, so no native wait handle is allocated.")]
internal sealed class McpCache<TKey, TValue>
    where TKey : notnull
{
    private readonly TimeProvider _timeProvider;
    private readonly ConcurrentDictionary<TKey, CacheState> _states;
    private readonly SemaphoreSlim _stateGate = new(1, 1);
    private readonly McpCacheOptions? _options;
    private int _entryCount;
    private long _totalSize;

    /// <summary>
    /// Initializes a new instance of the <see cref="McpCache{TKey, TValue}"/> class.
    /// </summary>
    /// <param name="timeProvider">The clock used to check expiration.</param>
    /// <param name="comparer">The comparer used for cache keys.</param>
    /// <param name="options">Optional limits for the number and combined size of cached entries.</param>
    /// <exception cref="ArgumentOutOfRangeException">A configured limit is not positive.</exception>
    public McpCache(TimeProvider timeProvider, IEqualityComparer<TKey> comparer, McpCacheOptions? options = null)
    {
        this._timeProvider = Throw.IfNull(timeProvider);
        this._states = new(Throw.IfNull(comparer));
        this._options = options;

        if (options?.MaxEntryCount is int maxEntryCount)
        {
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxEntryCount, nameof(options.MaxEntryCount));
        }

        if (options?.MaxTotalSize is long maxTotalSize)
        {
            ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxTotalSize, nameof(options.MaxTotalSize));
        }
    }

    /// <summary>
    /// Returns a fresh cached value or invokes the callback to refresh it after earlier reads of the same key finish.
    /// </summary>
    /// <remarks>
    /// The callback receives the previous entry, including expired content, or null if nothing is cached.
    /// An optional condition requests a refresh even when the entry is fresh; it is checked after earlier reads finish.
    /// Returning the previous entry preserves its lifetime. Failed or canceled refreshes leave the cache unchanged.
    /// A refreshed entry that would exceed the configured limits is rejected, and the previous entry is kept.
    /// </remarks>
    /// <exception cref="InvalidOperationException">The refreshed entry exceeds a cache limit or has no size when one is required.</exception>
    public async ValueTask<TValue> GetOrRefreshAsync(
        TKey key,
        Func<McpCacheEntry<TValue>?, CancellationToken, ValueTask<McpCacheEntry<TValue>>> refresh,
        CancellationToken cancellationToken,
        Predicate<TValue>? needsRefresh = null)
    {
        _ = Throw.IfNull(refresh);

        // This signal lets the next read run, even if this read fails or is canceled.
        TaskCompletionSource completion = new(TaskCreationOptions.RunContinuationsAsynchronously);

        // Queue this read. Other keys can still be fetched in parallel.
        (CacheState state, Task previous) = await this.RegisterReadAsync(key, completion.Task, cancellationToken).ConfigureAwait(false);

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

            var entry = Throw.IfNull(await refresh(cached, cancellationToken).ConfigureAwait(false));
            cancellationToken.ThrowIfCancellationRequested();

            if (this._options is null)
            {
                Volatile.Write(ref state.Entry, entry);
            }
            else
            {
                await this.StoreWithinLimitsAsync(key, state, entry, this._options, cancellationToken).ConfigureAwait(false);
            }

            return entry.Value;
        }
        finally
        {
            // Release later readers even if this read fails or is canceled.
            _ = this.CompleteQueuedReadAsync(key, state, previous, completion);
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
    /// Gets the number of keys with cached content or pending reads.
    /// </summary>
    internal int Count => this._states.Count;

    /// <summary>
    /// Stores an entry if it fits within the cache's count and size limits.
    /// </summary>
    /// <remarks>
    /// If a limit would be exceeded, the cache is left unchanged.
    /// </remarks>
    /// <param name="key">The cache key for the entry.</param>
    /// <param name="state">The state holding this key's previous entry, if any.</param>
    /// <param name="newEntry">The entry to store in place of the previous entry.</param>
    /// <param name="options">The limits on cached entry count and combined size.</param>
    /// <param name="cancellationToken">The token used to cancel storing the entry.</param>
    private async Task StoreWithinLimitsAsync(TKey key, CacheState state, McpCacheEntry<TValue> newEntry, McpCacheOptions options, CancellationToken cancellationToken)
    {
        // Without a size, the total-size limit cannot be checked.
        if (options.MaxTotalSize is not null && newEntry.Size is null)
        {
            throw new InvalidOperationException($"Caching '{key}' requires a size because the cache limits the total size of entries.");
        }

        // Missing sizes contribute zero when only the entry count is limited.
        long newSize = newEntry.Size ?? 0;

        // Other keys can finish fetching in parallel; check capacity and update totals one at a time.
        await this._stateGate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            var previousEntry = state.Entry;
            long previousSize = previousEntry?.Size ?? 0;

            // Check the count limit only when adding an entry; replacing an existing entry does not increase the count.
            if (previousEntry is null && options.MaxEntryCount is int maxEntryCount && this._entryCount >= maxEntryCount)
            {
                throw new InvalidOperationException($"Caching '{key}' would exceed the limit of {maxEntryCount} entries.");
            }

            // Check the size limit excluding this key's previous size, because the new entry replaces it.
            // E.g. with a limit of 100, a total of 90, and a previous size of 30, the new entry can be up to 40.
            if (options.MaxTotalSize is long maxTotalSize && newSize > maxTotalSize - (this._totalSize - previousSize))
            {
                throw new InvalidOperationException($"Caching '{key}' would exceed the total size limit of {maxTotalSize}.");
            }

            // Change the totals only after all checks pass.
            this._entryCount += previousEntry is null ? 1 : 0;
            this._totalSize += newSize - previousSize;

            // Publish the entry to readers that do not acquire the gate.
            Volatile.Write(ref state.Entry, newEntry);
        }
        finally
        {
            this._stateGate.Release();
        }
    }

    /// <summary>
    /// Queues a read and returns the key's cache state and the task it must wait for.
    /// </summary>
    private async Task<(CacheState State, Task Previous)> RegisterReadAsync(TKey key, Task completionTask, CancellationToken cancellationToken)
    {
        // Prevent cleanup from removing the state before this read is queued.
        await this._stateGate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (!this._states.TryGetValue(key, out CacheState? state))
            {
                state = new();
                this._states[key] = state;
            }

            // Chain reads so only one read per key runs at a time.
            // For the same key: A runs, B waits for A, and C waits for B.
            Task previous = state.Tail;
            state.Tail = completionTask;

            return (state, previous);
        }
        finally
        {
            this._stateGate.Release();
        }
    }

    /// <summary>
    /// Releases the next reader without letting it skip an earlier read.
    /// </summary>
    private async Task CompleteQueuedReadAsync(TKey key, CacheState state, Task previous, TaskCompletionSource completion)
    {
        // Do not cancel cleanup: later reads must still wait for the previous read.
        await previous.ConfigureAwait(false);

        await this._stateGate.WaitAsync().ConfigureAwait(false);
        try
        {
            // Remove the state only when no cached content or later reads remain.
            // If A fails with no cached content (state.Entry is null), keep the state while B waits.
            // If B also fails and no one else is queued, remove it.
            if (Volatile.Read(ref state.Entry) is null && ReferenceEquals(state.Tail, completion.Task))
            {
                this._states.TryRemove(key, out _);
            }
        }
        finally
        {
            this._stateGate.Release();
        }

        completion.SetResult();
    }

    /// <summary>
    /// Holds a cached entry and the last queued read for one key.
    /// </summary>
    private sealed class CacheState
    {
        /// <summary>
        /// The cached entry, or <see langword="null"/> if nothing is cached.
        /// </summary>
        public McpCacheEntry<TValue>? Entry;

        /// <summary>
        /// The last queued read, which the next reader waits for.
        /// </summary>
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
/// Pairs a cached value with its size and lifetime.
/// </summary>
internal sealed class McpCacheEntry<T>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="McpCacheEntry{T}"/> class without a size.
    /// </summary>
    /// <param name="value">The cached value.</param>
    /// <param name="lifetime">The lifetime used to check whether the value is fresh.</param>
    /// <remarks>Use the overload with a size when the cache has a total-size limit.</remarks>
    public McpCacheEntry(T value, McpCacheLifetime lifetime)
    {
        this.Value = value;
        this.Lifetime = Throw.IfNull(lifetime);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="McpCacheEntry{T}"/> class.
    /// </summary>
    /// <param name="value">The cached value.</param>
    /// <param name="size">The value's size, used to enforce the cache's total-size limit.</param>
    /// <param name="lifetime">The lifetime used to check whether the value is fresh.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="size"/> is negative.</exception>
    public McpCacheEntry(T value, long size, McpCacheLifetime lifetime)
        : this(value, lifetime)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(size);

        this.Size = size;
    }

    /// <summary>
    /// Gets the cached value.
    /// </summary>
    public T Value { get; }

    /// <summary>
    /// Gets the value's size, or <see langword="null"/> if no size was provided.
    /// </summary>
    public long? Size { get; }

    /// <summary>
    /// Gets the lifetime used to check whether the value is fresh.
    /// </summary>
    public McpCacheLifetime Lifetime { get; }
}

/// <summary>
/// Configures limits for an <see cref="McpCache{TKey, TValue}"/>.
/// </summary>
internal sealed class McpCacheOptions
{
    /// <summary>
    /// Gets the maximum number of cached entries, or <see langword="null"/> for no limit.
    /// </summary>
    public int? MaxEntryCount { get; init; }

    /// <summary>
    /// Gets the maximum combined size of cached entries, or <see langword="null"/> for no limit.
    /// </summary>
    /// <remarks>Entries must provide a size when this limit is set.</remarks>
    public long? MaxTotalSize { get; init; }
}
