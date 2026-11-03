// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="AgentMcpSkillsSource"/>.
/// </summary>
/// <remarks>
/// Listed discovery limits bound page counts and total skill counts.
/// The listed resource size limit separately bounds resource content processed by this source.
/// These limits do not bound incoming message size, list-response JSON size, or total memory consumption.
/// Application developers are responsible for evaluating server trustworthiness and configuring appropriate
/// input-size and resource limits through their chosen MCP client, transport, or hosting environment.
/// See <see cref="AgentSkillsProviderBuilderMcpExtensions.UseMcpSkills"/> for security considerations.
/// </remarks>
public sealed class AgentMcpSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets a callback that returns a key identifying the current caller, such as a user or tenant ID.
    /// The source keeps a separate skill cache for each key.
    /// </summary>
    /// <remarks>
    /// <para>
    /// MCP servers mark each response as <c>public</c> (the same for every caller) or <c>private</c>
    /// (specific to the caller's credentials) using <c>cacheScope</c>. A missing or <see langword="null"/>
    /// <c>cacheScope</c> is treated as <c>public</c>.
    /// </para>
    /// <para>
    /// When this callback is <see langword="null"/> (the default), the source cannot tell callers apart, so all callers
    /// share one cache and only public responses are accepted. A private response throws <see cref="InvalidOperationException"/>.
    /// </para>
    /// <para>
    /// When this callback is set, each key gets its own cache, so cached skills are never shared between keys,
    /// and private responses are accepted. Set it if the source is shared by several users or tenants,
    /// or if the server returns private responses, even for a single user.
    /// </para>
    /// <para>
    /// The callback runs on every skill discovery call and must return a non-empty key that matches the credentials
    /// the MCP client sends. Use an opaque ID, not an access token. Do not share returned skills between callers.
    /// Call <see cref="AgentSkillsProviderBuilder.DisableCaching"/> so the provider calls this source, and therefore
    /// this callback, every time.
    /// </para>
    /// </remarks>
    public Func<AgentSkillsSourceContext, string>? CacheIsolationKeySelector { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of cache partitions to keep, one per key returned by
    /// <see cref="CacheIsolationKeySelector"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), there is no limit, and a partition is kept for every key until the source is disposed.
    /// Set a limit for services with many users. When the limit is reached, skills for a new key are still returned,
    /// but are fetched from the server again on the next call. Must not be negative.
    /// </remarks>
    public int? MaxCachedPartitions { get; set; }

    /// <summary>
    /// Gets or sets how long a cache partition is kept after it was last used.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), unused partitions are kept until the source is disposed.
    /// Set it to free memory used by inactive users. After a partition is removed, the next call for its key
    /// fetches skills from the server again. Must be positive.
    /// To control how long MCP responses are cached, use <see cref="TtlResolver"/>.
    /// </remarks>
    public TimeSpan? PartitionSlidingExpiration { get; set; }

    /// <summary>
    /// Gets or sets how long a cache partition is kept after it was created, even if it is still in use.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), partitions have no maximum lifetime.
    /// After a partition is removed, the next call for its key fetches skills from the server again. Must be positive.
    /// To control how long MCP responses are cached, use <see cref="TtlResolver"/>.
    /// </remarks>
    public TimeSpan? PartitionAbsoluteExpiration { get; set; }

    /// <summary>
    /// Gets or sets a callback that determines the cache duration for each skill-list page, skill metadata, and resource response.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The MCP specification requires a TTL, but some servers may not provide it.
    /// When this property is <see langword="null"/>, positive server TTLs are used unchanged;
    /// missing, zero, or negative TTLs cause a fetch on every access.
    /// </para>
    /// <para>
    /// The callback receives the server TTL, or <see langword="null"/> if missing, and returns the cache duration.
    /// Positive results set the duration from response receipt; zero or negative results cause a fetch on the next access.
    /// Extending TTLs delays observing server changes but does not bypass content validation.
    /// </para>
    /// </remarks>
    public Func<TimeSpan?, TimeSpan>? TtlResolver { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of <c>skills/list</c> pages requested per discovery.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>10</c>. Must be positive.
    /// Empty pages count toward this limit. Discovery fails rather than returning a partial catalog
    /// when the last allowed page includes a continuation cursor.
    /// </remarks>
    public int? ListedMaxPageCount { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of skills accepted across all <c>skills/list</c> pages per discovery.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>100</c>. Must be positive.
    /// Every entry counts, including duplicate skill URIs. Discovery fails if the limit is exceeded.
    /// </remarks>
    public int? ListedMaxSkillCount { get; set; }

    /// <summary>
    /// Gets or sets the maximum size, in bytes, of a resource discovered through <c>skills/list</c>,
    /// including <c>SKILL.md</c>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>1 MiB</c> (<c>1,048,576</c> bytes).
    /// Must be positive. Discovery rejects resources whose advertised sizes exceed the limit.
    /// Reads also check actual UTF-8 text and decoded binary sizes before encoding text or decoding
    /// blobs for integrity verification.
    /// There is no combined resource-size limit per skill.
    /// </remarks>
    public long? ListedResourceMaxSizeBytes { get; set; }

    /// <summary>
    /// Creates cache options from the partition retention settings.
    /// </summary>
    internal MemoryCacheOptions ToMemoryCacheOptions() => new()
    {
        SizeLimit = this.MaxCachedPartitions
    };

    /// <summary>
    /// Creates entry options from the partition retention settings.
    /// </summary>
    internal MemoryCacheEntryOptions ToMemoryCacheEntryOptions() => new()
    {
        Size = 1,
        SlidingExpiration = this.PartitionSlidingExpiration,
        AbsoluteExpirationRelativeToNow = this.PartitionAbsoluteExpiration
    };
}
