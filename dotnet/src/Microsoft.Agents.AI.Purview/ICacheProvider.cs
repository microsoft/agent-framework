// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Manages caching of values.
/// </summary>
internal interface ICacheProvider
{
    /// <summary>
    /// Get a value from the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key in the cache. Used for serialization.</typeparam>
    /// <typeparam name="TValue">The type of the value in the cache. Used for serialization.</typeparam>
    /// <param name="key">The key to look up in the cache.</param>
    /// <param name="cancellationToken">A cancellation token for the async operation.</param>
    /// <returns>The value in the cache. Null or default if no value is present.</returns>
    Task<TValue?> GetAsync<TKey, TValue>(TKey key, CancellationToken cancellationToken);

    /// <summary>
    /// Set a value in the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key in the cache. Used for serialization.</typeparam>
    /// <typeparam name="TValue">The type of the value in the cache. Used for serialization.</typeparam>
    /// <param name="key">The key to identify the cache entry.</param>
    /// <param name="value">The value to cache.</param>
    /// <param name="cancellationToken">A cancellation token for the async operation.</param>
    /// <returns>A task for the async operation.</returns>
    Task SetAsync<TKey, TValue>(TKey key, TValue value, CancellationToken cancellationToken);

    /// <summary>
    /// Removes a value from the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key.</typeparam>
    /// <param name="key">The key to identify the cache entry.</param>
    /// <param name="cancellationToken">The cancellation token for the async operation.</param>
    /// <returns>A task for the async operation.</returns>
    Task RemoveAsync<TKey>(TKey key, CancellationToken cancellationToken);
}
