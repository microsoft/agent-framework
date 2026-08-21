// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source decorator that caches the result of the inner source's <see cref="AgentSkillsSource.GetSkillsAsync"/>
/// call, returning the cached list on subsequent invocations.
/// </summary>
/// <remarks>
/// <para>
/// Concurrent callers are serialized per cache key so that only one underlying fetch runs at a time.
/// Once a fetch succeeds, the result is cached and shared by all subsequent callers.
/// </para>
/// <para>
/// When <see cref="CachingAgentSkillsSourceOptions.RefreshInterval"/> is set, a cached result is
/// returned only while it is younger than the interval; once it expires, the next caller re-invokes
/// the inner source and replaces the cached result. When the interval is <see langword="null"/>, the
/// cached result never expires.
/// </para>
/// <para>
/// The fetch observes the initiating caller's cancellation token. If that caller cancels, the fetch is
/// cancelled and the result is not cached; the next waiting caller starts a fresh fetch. Likewise, a fetch
/// that fails is not cached and subsequent calls will retry.
/// </para>
/// </remarks>
public sealed class CachingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private const string SharedCacheKey = "CachingAgentSkillsSource-SharedCacheKey";

    private readonly ConcurrentDictionary<string, CacheEntry> _cachedEntries = new(StringComparer.Ordinal);
    private readonly CachingAgentSkillsSourceOptions? _options;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="CachingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source whose results will be cached.</param>
    /// <param name="options">Optional cache configuration.</param>
    public CachingAgentSkillsSource(AgentSkillsSource innerSource, CachingAgentSkillsSourceOptions? options = null)
        : base(innerSource)
    {
        this._options = options;
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();

        var cacheKey = this._options?.CacheIsolationKeySelector?.Invoke(context) ?? SharedCacheKey;

        var entry = this._cachedEntries.GetOrAdd(cacheKey, _ => new CacheEntry());

        // Fast path: a fresh result has already been fetched and cached.
        if (this.TryGetFreshResult(entry) is { } cached)
        {
            return cached;
        }

        // Only one caller fetches at a time for a given cache key; the rest queue here.
        await entry.Gate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            // Another caller may have populated (or refreshed) the cache while we waited on the gate.
            if (this.TryGetFreshResult(entry) is { } existing)
            {
                return existing;
            }

            // The fetch uses the caller's token. If the caller cancels (or the fetch fails),
            // the result is not cached and the next waiting caller starts a fresh fetch.
            var result = await this.InnerSource.GetSkillsAsync(context, cancellationToken).ConfigureAwait(false);
            entry.Result = result;
            entry.LastRefreshedUtc = DateTime.UtcNow;
            return result;
        }
        finally
        {
            entry.Gate.Release();
        }
    }

    /// <summary>
    /// Returns the cached result for the entry when it exists and is still fresh; otherwise <see langword="null"/>.
    /// </summary>
    private IList<AgentSkill>? TryGetFreshResult(CacheEntry entry)
    {
        if (entry.Result is not { } result)
        {
            return null;
        }

        if (this._options?.RefreshInterval is { } interval &&
            DateTime.UtcNow - entry.LastRefreshedUtc >= interval)
        {
            return null;
        }

        return result;
    }

    private void ThrowIfDisposed()
    {
#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing && !this._disposed)
        {
            this._disposed = true;

            foreach (var entry in this._cachedEntries.Values)
            {
                entry.Gate.Dispose();
            }

            base.Dispose(disposing);
        }
    }

    /// <summary>
    /// A single cache slot: a gate that serializes fetches for one cache key, plus the cached result.
    /// </summary>
    private sealed class CacheEntry
    {
        /// <summary>Gets the gate that ensures only one fetch runs at a time for this cache key.</summary>
        public SemaphoreSlim Gate { get; } = new(1, 1);

        /// <summary>Gets or sets the cached result, or <see langword="null"/> if it has not been fetched yet.</summary>
        public IList<AgentSkill>? Result { get; set; }

        /// <summary>Gets or sets the UTC time at which <see cref="Result"/> was last refreshed.</summary>
        public DateTime LastRefreshedUtc { get; set; }
    }
}
