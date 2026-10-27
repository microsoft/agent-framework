// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Caches the skill list and coordinates full and individual skill refreshes.
/// </summary>
/// <remarks>
/// <para>
/// The supplied callbacks fetch the complete skill list or updated details for one skill.
/// The loader stores the list with its lifetime and returns it until it expires, unless a skill refresh is queued.
/// A missing or expired cached list is fetched in full on the next <see cref="GetSkillsAsync"/> call.
/// </para>
/// <para>
/// When fetched resource content differs from its expected size or content hash, the owning skill
/// calls <see cref="QueueSkillRefresh"/>. This records a request; it does not fetch updated details immediately.
/// On the next <see cref="GetSkillsAsync"/> call, queued skills are refreshed individually if the cached list
/// has not expired. Otherwise, fetching the complete list replaces the need for individual refreshes.
/// Resource reads and resource-content caching remain the responsibility of each skill object.
/// </para>
/// <para>
/// An individual refresh replaces the skill object, or removes it if the callback reports that it no longer exists.
/// The updated list is stored only after all queued refreshes in that batch succeed, without extending the list's lifetime.
/// Failures leave the previous list and pending refresh requests available for retry on a later call.
/// Previously returned lists and skill objects remain unchanged.
/// </para>
/// <para>
/// Only one caller can fetch or update the skill list at a time; other callers wait and then check the cache again.
/// No refreshes run in the background. Disposing the loader clears its cached list and pending requests,
/// but does not dispose the MCP client or prevent previously returned skills from reading resources.
/// </para>
/// </remarks>
internal sealed class McpSkillsLoader : IDisposable
{
    private const string CatalogKey = "catalog";

    private readonly Func<CancellationToken, Task<McpCacheEntry<IList<AgentSkill>>>> _fetchSkills;
    private readonly Func<string, CancellationToken, Task<AgentMcpSkill?>> _fetchSkill;
    private readonly McpCache<string, IList<AgentSkill>> _catalogCache;
    private readonly ConcurrentDictionary<AgentMcpSkill, byte> _skillsToRefresh = new();
    private readonly SemaphoreSlim _discoveryGate = new(1, 1);
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="McpSkillsLoader"/> class.
    /// </summary>
    /// <param name="timeProvider">The clock for checking list expiration.</param>
    /// <param name="fetchSkills">Fetches the complete skill list with the lifetime used to cache it.</param>
    /// <param name="fetchSkill">Fetches updated details for a skill URI and returns a replacement object, or null if the skill no longer exists.</param>
    public McpSkillsLoader(
        TimeProvider timeProvider,
        Func<CancellationToken, Task<McpCacheEntry<IList<AgentSkill>>>> fetchSkills,
        Func<string, CancellationToken, Task<AgentMcpSkill?>> fetchSkill)
    {
        _ = Throw.IfNull(timeProvider);
        this._fetchSkills = Throw.IfNull(fetchSkills);
        this._fetchSkill = Throw.IfNull(fetchSkill);
        this._catalogCache = new(timeProvider, StringComparer.Ordinal);
    }

    /// <summary>
    /// Returns the skill list, fetching it if missing or expired, or applying queued skill refreshes otherwise.
    /// </summary>
    /// <param name="cancellationToken">The token used to cancel waiting or fetching.</param>
    /// <returns>The cached or updated skill list.</returns>
    public async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, this);
        cancellationToken.ThrowIfCancellationRequested();

        // Reuse the catalog only while every page is fresh.
        if (this._catalogCache.Get(CatalogKey) is { } cached && this._catalogCache.IsFresh(cached) && this._skillsToRefresh.IsEmpty)
        {
            return cached.Value;
        }

        // Allow only one caller to discover or refresh the catalog at a time.
        await this._discoveryGate.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Another caller may have refreshed the cache while this caller waited.
            cached = this._catalogCache.Get(CatalogKey);
            if (cached is not null && this._catalogCache.IsFresh(cached))
            {
                return await this.RefreshPendingSkillsAsync(cached, cancellationToken).ConfigureAwait(false);
            }

            // Reloading all pages also updates queued skills, so there is no need to refresh them separately.
            var skillsEntry = await this._fetchSkills(cancellationToken).ConfigureAwait(false);

            cancellationToken.ThrowIfCancellationRequested();

            this.UpdateCatalogCache(skillsEntry);

            return skillsEntry.Value;
        }
        finally
        {
            this._discoveryGate.Release();
        }
    }

    /// <summary>
    /// Queues a skill from the cached list for refresh on the next <see cref="GetSkillsAsync"/> call.
    /// </summary>
    /// <remarks>
    /// Called after a resource's size or content hash differs from the values recorded for its owning skill.
    /// Requests for skill objects no longer in the cached list, or made after disposal, are ignored.
    /// </remarks>
    /// <param name="skill">The skill object whose server-provided details need to be fetched again.</param>
    public void QueueSkillRefresh(AgentMcpSkill skill)
    {
        _ = Throw.IfNull(skill);

        // Ignore refresh requests after disposal or when the skill is no longer in the cache.
        if (!this._disposed && this._catalogCache.Get(CatalogKey)?.Value.Contains(skill) == true)
        {
            this._skillsToRefresh.TryAdd(skill, 0);
        }
    }

    /// <summary>
    /// Refreshes queued skills and stores the updated list only if every refresh succeeds.
    /// </summary>
    /// <remarks>
    /// Replaces updated skills and removes missing ones in a new list, keeping the cached list's expiration time.
    /// If a fetch fails or is canceled, the previous list and pending requests remain available for retry.
    /// </remarks>
    private async Task<IList<AgentSkill>> RefreshPendingSkillsAsync(McpCacheEntry<IList<AgentSkill>> cached, CancellationToken cancellationToken)
    {
        List<AgentSkill>? updated = null;

        foreach (AgentMcpSkill skill in this._skillsToRefresh.Keys)
        {
            // Discard obsolete requests
            if (!cached.Value.Contains(skill))
            {
                this._skillsToRefresh.TryRemove(skill, out _);
                continue;
            }

            AgentMcpSkill? replacement = await this._fetchSkill(skill.Uri, cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();

            // Keep previously returned lists and skill instances unchanged.
            updated ??= [.. cached.Value];

            int index = updated.IndexOf(skill);

            if (replacement is null)
            {
                // The server no longer advertises this skill.
                updated.RemoveAt(index);
            }
            else
            {
                updated[index] = replacement;
            }
        }

        if (updated is null)
        {
            return cached.Value;
        }

        cancellationToken.ThrowIfCancellationRequested();

        // Commit only after every refresh succeeds; failures leave the catalog and pending work intact.
        // Targeted refreshes do not renew the listing-page lifetime.
        this.UpdateCatalogCache(new(updated, cached.Lifetime));

        return updated;
    }

    /// <summary>
    /// Stores the skill list and removes pending refresh requests for skill objects no longer in that list.
    /// </summary>
    private void UpdateCatalogCache(McpCacheEntry<IList<AgentSkill>> entry)
    {
        this._catalogCache.Set(CatalogKey, entry);

        // Keep requests for skills still in the list: they may have been queued during the refresh
        // or just after the new catalog was stored.
        foreach (AgentMcpSkill skill in this._skillsToRefresh.Keys)
        {
            if (!entry.Value.Contains(skill))
            {
                this._skillsToRefresh.TryRemove(skill, out _);
            }
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;
            this._catalogCache.Clear();
            this._skillsToRefresh.Clear();
            this._discoveryGate.Dispose();
        }
    }
}
