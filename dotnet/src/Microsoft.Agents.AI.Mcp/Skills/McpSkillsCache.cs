// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Caches MCP-listed skills until any page's TTL expires.
/// </summary>
internal sealed class McpSkillsCache : IDisposable
{
    private readonly TimeProvider _timeProvider;
    private readonly Func<CancellationToken, Task<McpSkillsSnapshot>> _discoverSkills;
    private readonly SemaphoreSlim _discoveryGate = new(1, 1);
    private volatile McpSkillsSnapshot? _cachedSnapshot;
    private bool _disposed;

    /// <summary>
    /// Initializes a cache using the clock that records discovery page receipt timestamps.
    /// </summary>
    /// <param name="timeProvider">The clock for checking page freshness.</param>
    /// <param name="discoverSkills">Discovers and validates all pages, including their receipt timestamps and TTLs.</param>
    public McpSkillsCache(TimeProvider timeProvider, Func<CancellationToken, Task<McpSkillsSnapshot>> discoverSkills)
    {
        this._timeProvider = Throw.IfNull(timeProvider);
        this._discoverSkills = Throw.IfNull(discoverSkills);
    }

    /// <summary>
    /// Gets fresh cached skills or invokes discovery to replace the catalog.
    /// </summary>
    /// <param name="cancellationToken">The token used to cancel waiting or discovery.</param>
    /// <returns>The cached or newly discovered skills.</returns>
    public async Task<IList<AgentSkill>> GetOrCreateAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, this);
        cancellationToken.ThrowIfCancellationRequested();

        // Reuse the catalog only while every page is fresh.
        if (this.GetCachedSnapshot() is { } cached)
        {
            return cached.Skills;
        }

        // Allow only one caller to discover or refresh the catalog at a time.
        await this._discoveryGate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Another caller may have refreshed the cache while this caller waited.
            cached = this.GetCachedSnapshot();
            if (cached is not null)
            {
                return cached.Skills;
            }

            // Refresh all pages from the beginning.
            var snapshot = await this._discoverSkills(cancellationToken).ConfigureAwait(false);

            cancellationToken.ThrowIfCancellationRequested();

            this.CacheSnapshot(snapshot);

            return snapshot.Skills;
        }
        finally
        {
            this._discoveryGate.Release();
        }
    }

    /// <summary>
    /// Gets the cached snapshot, or <see langword="null"/> if it is absent or any listing page has expired.
    /// </summary>
    private McpSkillsSnapshot? GetCachedSnapshot()
    {
        if (this._cachedSnapshot is not { } cached)
        {
            return null;
        }

        long now = this._timeProvider.GetTimestamp();

        // Check every page against the same timestamp. Any expired page makes the catalog stale.
        foreach (McpSkillsPageLifetime page in cached.PageLifetimes)
        {
            if (this._timeProvider.GetElapsedTime(page.ReceivedTimestamp, now) >= page.TimeToLive)
            {
                return null;
            }
        }

        return cached;
    }

    /// <summary>
    /// Stores the snapshot.
    /// </summary>
    /// <param name="snapshot">The skill list and its listing-page lifetimes.</param>
    private void CacheSnapshot(McpSkillsSnapshot snapshot)
    {
        // Publish the complete catalog and page lifetimes together only after discovery and validation succeed.
        this._cachedSnapshot = snapshot;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;
            this._discoveryGate.Dispose();
        }
    }
}
