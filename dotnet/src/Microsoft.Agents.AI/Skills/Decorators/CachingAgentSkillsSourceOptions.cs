// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring <see cref="CachingAgentSkillsSource"/>.
/// </summary>
public sealed class CachingAgentSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets a delegate that returns the cache isolation key for a skills source invocation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When this delegate is <see langword="null"/>, or when it returns <see langword="null"/>,
    /// the skills are stored in the shared cache bucket. When it returns a non-null string,
    /// the skills are cached under that key.
    /// </para>
    /// <para>
    /// The isolation key should be low-cardinality and stable.
    /// High-cardinality keys (for example, per-session IDs) can cause the cache to grow without bound.
    /// </para>
    /// </remarks>
    public Func<AgentSkillsSourceContext, string?>? CacheIsolationKeySelector { get; set; }

    /// <summary>
    /// Gets or sets the interval after which a cached skill list is considered stale and is refreshed
    /// from the inner source on the next request.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), cached results never expire and the inner source is
    /// invoked only once per cache key. Set to a positive <see cref="TimeSpan"/> to re-invoke the inner
    /// source once the cached result is older than the interval. Values of <see cref="TimeSpan.Zero"/> or
    /// negative durations effectively disable caching because the cached result is always considered stale.
    /// </remarks>
    public TimeSpan? RefreshInterval { get; set; }
}
