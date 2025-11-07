// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
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
    private static readonly ConcurrentDictionary<(IMemoryCache, object), SemaphoreSlim> s_semaphores = new();

    /// <summary>
    /// Atomically gets the value associated with this key if it exists, or generates a new entry
    /// using the provided key and a value from the given factory if the key is not found.
    /// </summary>
    /// <typeparam name="T">The type of the object to get.</typeparam>
    /// <param name="memoryCache">The <see cref="IMemoryCache"/> instance this method extends.</param>
    /// <param name="key">The key of the entry to look for or create.</param>
    /// <param name="factory">The factory that creates the value associated with this key if the key does not exist in the cache.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A tuple containing the value and a flag indicating whether it was created (true) or retrieved from cache (false).</returns>
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

        // Get or create a semaphore for this cache key
        bool isOwner = false;
        var semaphoreKey = (memoryCache, key);
        if (!s_semaphores.TryGetValue(semaphoreKey, out SemaphoreSlim? semaphore))
        {
            SemaphoreSlim? createdSemaphore = null;
            semaphore = s_semaphores.GetOrAdd(semaphoreKey, _ => createdSemaphore = new SemaphoreSlim(1));

            // If we created the semaphore that made it into the dictionary, we're the owner
            if (ReferenceEquals(createdSemaphore, semaphore))
            {
                isOwner = true;
            }
            else
            {
                // Our semaphore wasn't the one stored, so dispose it
                createdSemaphore?.Dispose();
            }
        }

        await semaphore.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
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
            // If we were the owner of the semaphore, remove it from the dictionary
            // This prevents memory leaks from accumulating semaphores for evicted cache entries
            if (isOwner)
            {
                s_semaphores.TryRemove(semaphoreKey, out _);
            }

            semaphore.Release();
        }
    }
}
