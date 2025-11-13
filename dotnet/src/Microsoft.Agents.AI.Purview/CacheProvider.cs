// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Serialization;
using Microsoft.Extensions.Caching.Distributed;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Manages caching of values.
/// </summary>
internal sealed class CacheProvider : ICacheProvider
{
    private readonly IDistributedCache _cache;
    private readonly PurviewSettings _purviewSettings;

    /// <summary>
    /// Create a new instance of the <see cref="CacheProvider"/> class.
    /// </summary>
    /// <param name="cache">The cache where the data is stored.</param>
    /// <param name="purviewSettings">The purview integration settings.</param>
    public CacheProvider(IDistributedCache cache, PurviewSettings purviewSettings)
    {
        this._cache = cache;
        this._purviewSettings = purviewSettings;
    }

    /// <summary>
    /// Get a value from the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key in the cache. Used for serialization.</typeparam>
    /// <typeparam name="TValue">The type of the value in the cache. Used for serialization.</typeparam>
    /// <param name="key">The key to look up in the cache.</param>
    /// <param name="cancellationToken">A cancellation token for the async operation.</param>
    /// <returns>The value in the cache. Null or default if no value is present.</returns>
    public async Task<TValue?> GetAsync<TKey, TValue>(TKey key, CancellationToken cancellationToken)
    {
        JsonTypeInfo<TKey> keyTypeInfo = (JsonTypeInfo<TKey>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(TKey));
        string serializedKey = JsonSerializer.Serialize(key, keyTypeInfo);
        byte[]? data = await this._cache.GetAsync(serializedKey, cancellationToken).ConfigureAwait(false);
        if (data == null)
        {
            return default;
        }

        JsonTypeInfo<TValue> valueTypeInfo = (JsonTypeInfo<TValue>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(TValue));

        return JsonSerializer.Deserialize(data, valueTypeInfo);
    }

    /// <summary>
    /// Set a value in the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key in the cache. Used for serialization.</typeparam>
    /// <typeparam name="TValue">The type of the value in the cache. Used for serialization.</typeparam>
    /// <param name="key">The key to identify the cache entry.</param>
    /// <param name="value">The value to cache.</param>
    /// <param name="cancellationToken">A cancellation token for the async operation.</param>
    /// <returns>A task for the async operation.</returns>
    public Task SetAsync<TKey, TValue>(TKey key, TValue value, CancellationToken cancellationToken)
    {
        JsonTypeInfo<TKey> keyTypeInfo = (JsonTypeInfo<TKey>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(TKey));
        string serializedKey = JsonSerializer.Serialize(key, keyTypeInfo);
        JsonTypeInfo<TValue> valueTypeInfo = (JsonTypeInfo<TValue>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(TValue));
        byte[] serializedValue = JsonSerializer.SerializeToUtf8Bytes(value, valueTypeInfo);

        DistributedCacheEntryOptions cacheOptions = new() { AbsoluteExpirationRelativeToNow = this._purviewSettings.CacheTTL };

        return this._cache.SetAsync(serializedKey, serializedValue, cacheOptions, cancellationToken);
    }

    /// <summary>
    /// Removes a value from the cache.
    /// </summary>
    /// <typeparam name="TKey">The type of the key.</typeparam>
    /// <param name="key">The key to identify the cache entry.</param>
    /// <param name="cancellationToken">The cancellation token for the async operation.</param>
    /// <returns>A task for the async operation.</returns>
    public Task RemoveAsync<TKey>(TKey key, CancellationToken cancellationToken)
    {
        JsonTypeInfo<TKey> keyTypeInfo = (JsonTypeInfo<TKey>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(TKey));
        string serializedKey = JsonSerializer.Serialize(key, keyTypeInfo);

        return this._cache.RemoveAsync(serializedKey, cancellationToken);
    }
}
