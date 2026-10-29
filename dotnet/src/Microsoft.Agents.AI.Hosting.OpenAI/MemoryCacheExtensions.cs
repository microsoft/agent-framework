// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Extension methods for <see cref="IMemoryCache"/> that provide atomic operations.
/// </summary>
/// <remarks>
/// The standard GetOrCreate method has a race condition where multiple threads can simultaneously
/// detect that a key doesn't exist and create different instances, with only one being cached.
/// See: https://github.com/dotnet/runtime/issues/36499
/// </remarks>
internal static class MemoryCacheExtensions
{
    private static readonly object s_syncRoot = new();
    private static readonly Dictionary<(IMemoryCache, object), CacheLock> s_locks = new();

    /// <summary>
    /// Atomically gets the value associated with this key if it exists, or generates a new entry
    /// using the provided key and a value from the given factory if the key is not found.
    /// </summary>
    /// <typeparam name="T">The type of the object to get.</typeparam>
    /// <param name="memoryCache">The <see cref="IMemoryCache"/> instance this method extends.</param>
    /// <param name="key">The key of the entry to look for or create.</param>
    /// <param name="factory">The factory that creates the value associated with this key if the key does not exist in the cache.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The cached or newly created value.</returns>
    public static async Task<T> GetOrCreateAtomicAsync<T>(
        this IMemoryCache memoryCache,
        object key,
        Func<ICacheEntry, T> factory,
        CancellationToken cancellationToken = default)
    {
        // Fast path: check if the value already exists
        if (memoryCache.TryGetValue(key, out object? value))
        {
            Debug.Assert(value is not null);
            return (T)value;
        }

        // Register both holders and waiters before touching the semaphore. A lock must remain
        // registered until its last caller leaves, even when a factory fails or a waiter cancels.
        var semaphoreKey = (memoryCache, key);
        CacheLock cacheLock;
        lock (s_syncRoot)
        {
            if (!s_locks.TryGetValue(semaphoreKey, out cacheLock!))
            {
                s_locks.Add(semaphoreKey, cacheLock = new CacheLock());
            }

            cacheLock.ReferenceCount++;
        }

        bool lockAcquired = false;
        try
        {
            await cacheLock.Semaphore.WaitAsync(cancellationToken).ConfigureAwait(false);
            lockAcquired = true;

            // Double-check: another thread might have created the value while we were waiting
            if (!memoryCache.TryGetValue(key, out value))
            {
                ICacheEntry entry = memoryCache.CreateEntry(key);
                entry.SetValue(value = factory(entry));
                entry.Dispose();
                Debug.Assert(value is not null);
                return (T)value;
            }

            Debug.Assert(value is not null);
            return (T)value;
        }
        finally
        {
            if (lockAcquired)
            {
                cacheLock.Semaphore.Release();
            }

            lock (s_syncRoot)
            {
                if (--cacheLock.ReferenceCount == 0)
                {
                    s_locks.Remove(semaphoreKey);
                    cacheLock.Semaphore.Dispose();
                }
            }
        }
    }

    /// <summary>Tracks all callers that can still use a cache key's semaphore.</summary>
    private sealed class CacheLock
    {
        /// <summary>Gets the semaphore that serializes factories for one cache key.</summary>
        public SemaphoreSlim Semaphore { get; } = new(1, 1);

        /// <summary>Gets or sets the caller count, accessed only while holding <see cref="s_syncRoot"/>.</summary>
        public int ReferenceCount { get; set; }
    }
}
