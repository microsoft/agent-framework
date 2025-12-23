// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Configuration options for in-memory storage implementations.
/// </summary>
internal sealed class InMemoryStorageOptions
{
    /// <summary>
    /// Gets or sets the maximum number of items to store in the cache.
    /// Default is 1000. Set to null for no size limit.
    /// </summary>
    public long? SizeLimit { get; set; } = 1000;

    /// <summary>
    /// Gets or sets the absolute expiration time for items in storage.
    /// If specified, items will be expired after this timespan regardless of access.
    /// Default is null (no absolute expiration).
    /// </summary>
    public TimeSpan? AbsoluteExpirationRelativeToNow { get; set; }

    /// <summary>
    /// Gets or sets the sliding expiration for items in storage.
    /// Items will be expired if not accessed within this timespan.
    /// Default is 1 hour.
    /// </summary>
    public TimeSpan? SlidingExpiration { get; set; } = TimeSpan.FromHours(1);

    /// <summary>
    /// Creates <see cref="MemoryCacheOptions"/> from these options.
    /// </summary>
    internal MemoryCacheOptions ToMemoryCacheOptions() => new()
    {
        SizeLimit = this.SizeLimit
    };

    /// <summary>
    /// Creates <see cref="MemoryCacheEntryOptions"/> from these options.
    /// </summary>
    internal MemoryCacheEntryOptions ToMemoryCacheEntryOptions() => new()
    {
        AbsoluteExpirationRelativeToNow = this.AbsoluteExpirationRelativeToNow,
        SlidingExpiration = this.SlidingExpiration,
        Size = 1
    };
}
