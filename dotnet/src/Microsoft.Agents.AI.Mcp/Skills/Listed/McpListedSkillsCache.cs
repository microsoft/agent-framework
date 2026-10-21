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
internal sealed class McpListedSkillsCache : IDisposable
{
    private readonly TimeProvider _timeProvider;
    private readonly SemaphoreSlim _discoveryGate = new(1, 1);
    private volatile McpListedSkillsDiscoveryResult? _cachedSkills;
    private bool _disposed;

    /// <summary>
    /// Initializes a cache using the clock that records discovery page receipt timestamps.
    /// </summary>
    /// <param name="timeProvider">The clock for checking page freshness.</param>
    public McpListedSkillsCache(TimeProvider timeProvider)
    {
        this._timeProvider = Throw.IfNull(timeProvider);
    }

    /// <summary>
    /// Gets fresh cached skills or invokes discovery to replace the catalog.
    /// </summary>
    /// <param name="discoverSkills">Discovers and validates all pages, including their receipt timestamps and TTLs.</param>
    /// <param name="cancellationToken">The token used to cancel waiting or discovery.</param>
    /// <returns>The cached or newly discovered skills.</returns>
    public async Task<IList<AgentSkill>> GetOrCreateAsync(Func<CancellationToken, Task<McpListedSkillsDiscoveryResult>> discoverSkills, CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, this);
        cancellationToken.ThrowIfCancellationRequested();

        // Reuse the catalog only while every page is fresh.
        if (this.GetCachedSkills() is { } cached)
        {
            return cached;
        }

        // Allow only one caller to discover or refresh the catalog at a time.
        await this._discoveryGate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Another caller may have refreshed the cache while this caller waited.
            cached = this.GetCachedSkills();
            if (cached is not null)
            {
                return cached;
            }

            // Refresh all pages from the beginning.
            var result = await discoverSkills(cancellationToken).ConfigureAwait(false);

            cancellationToken.ThrowIfCancellationRequested();

            this.CacheSkills(result);

            return result.Skills;
        }
        finally
        {
            this._discoveryGate.Release();
        }
    }

    /// <summary>
    /// Gets the cached skills, or <see langword="null"/> if the cache is absent or expired.
    /// </summary>
    private List<AgentSkill>? GetCachedSkills()
    {
        if (this._cachedSkills is not { } cached)
        {
            return null;
        }

        long now = this._timeProvider.GetTimestamp();

        // Check every page against the same timestamp. Any expired page makes the catalog stale.
        foreach (McpListedSkillsPageLifetime page in cached.PageLifetimes)
        {
            if (this._timeProvider.GetElapsedTime(page.ReceivedTimestamp, now) >= page.TimeToLive)
            {
                return null;
            }
        }

        return cached.Skills;
    }

    /// <summary>
    /// Caches the discovered skills together with their page lifetimes.
    /// </summary>
    /// <param name="result">The complete discovery result.</param>
    private void CacheSkills(McpListedSkillsDiscoveryResult result)
    {
        // Publish the complete catalog and page lifetimes together only after discovery and validation succeed.
        this._cachedSkills = result;
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
