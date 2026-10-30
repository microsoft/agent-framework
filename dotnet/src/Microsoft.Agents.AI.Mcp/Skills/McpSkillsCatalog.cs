// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// Discovers and validates skills from an MCP server and owns the cached catalog and its refreshes.
/// </summary>
/// <remarks>
/// <para>
/// Fetches and validates all <c>skills/list</c> pages before creating and publishing skill objects.
/// The source checks server support before accessing the catalog.
/// Configured limits bound discovery and resource sizes.
/// </para>
/// <para>
/// The list is cached until any page expires, then fetched again on the next <see cref="GetSkillsAsync"/> call.
/// Queued refresh requests and individual metadata expiration trigger <c>skills/get</c> while the list is fresh.
/// Full discovery takes priority when the list expires.
/// </para>
/// <para>
/// An individual refresh replaces the skill object, or removes it if the server no longer serves it.
/// The updated list is stored only after all refreshes in that batch succeed.
/// The list keeps its original lifetime; replacement responses control only their own skills' lifetimes.
/// Failures leave the previous list and pending refresh requests available for retry on a later call.
/// Previously returned lists and skill objects remain unchanged by refreshes.
/// </para>
/// <para>
/// Resource retrieval, verification, and content caching remain the responsibility of each skill object.
/// A size or digest mismatch queues a metadata refresh through <see cref="QueueSkillRefresh"/>.
/// </para>
/// <para>
/// Only one caller can fetch or update the skill list at a time; other callers wait and then check the cache again.
/// No refreshes run in the background. Disposing the catalog clears its cached list and pending requests,
/// but does not dispose the MCP client or prevent previously returned skills from reading resources.
/// </para>
/// </remarks>
internal sealed partial class McpSkillsCatalog : IDisposable
{
    private const string CatalogKey = "catalog";
    private const string CompleteResultType = "complete";
    private const int DefaultMaxPageCount = 10;
    private const int DefaultMaxSkillCount = 100;

    [SuppressMessage("Usage", "CA2213:Disposable fields should be disposed", Justification = "The MCP client is supplied and owned by the caller, who is responsible for disposing it.")]
    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly long _maxResourceSizeBytes;
    private readonly int _maxPageCount;
    private readonly int _maxSkillCount;
    private readonly TimeProvider _timeProvider;
    private readonly McpCache<string, IList<AgentSkill>> _catalogCache;
    private readonly ConcurrentDictionary<AgentMcpSkill, byte> _skillsToRefresh = new();
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="McpSkillsCatalog"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional limits for listing pages, skill counts, and resource sizes.</param>
    /// <param name="logger">Optional logger for skill validation diagnostics.</param>
    /// <param name="timeProvider">Optional clock for checking expiration.</param>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException">A configured limit is not positive.</exception>
    public McpSkillsCatalog(McpClient client, AgentMcpSkillsSourceOptions? options = null, ILogger? logger = null, TimeProvider? timeProvider = null)
    {
        this._client = Throw.IfNull(client);
        this._logger = logger ?? NullLogger.Instance;
        this._maxResourceSizeBytes = options?.ListedResourceMaxSizeBytes ?? AgentMcpSkill.DefaultMaxResourceSizeBytes;
        this._maxPageCount = options?.ListedMaxPageCount ?? DefaultMaxPageCount;
        this._maxSkillCount = options?.ListedMaxSkillCount ?? DefaultMaxSkillCount;
        this._timeProvider = timeProvider ?? TimeProvider.System;
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxResourceSizeBytes, nameof(options.ListedResourceMaxSizeBytes));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxPageCount, nameof(options.ListedMaxPageCount));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxSkillCount, nameof(options.ListedMaxSkillCount));
        this._catalogCache = new(this._timeProvider, StringComparer.Ordinal);
    }

    /// <summary>
    /// Returns the skill list, fetching it if missing or expired, or refreshing queued and expired skills otherwise.
    /// </summary>
    /// <param name="cancellationToken">The token used to cancel waiting or fetching.</param>
    /// <returns>The shared mutable skill list for the cached or updated catalog.</returns>
    public async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, this);
        cancellationToken.ThrowIfCancellationRequested();

        IList<AgentSkill> skills = await this._catalogCache.GetOrRefreshAsync(
            CatalogKey,
            this.RefreshCatalogAsync,
            cancellationToken,
            needsRefresh: cached => !this._skillsToRefresh.IsEmpty ||
                cached.OfType<AgentMcpSkill>().Any(skill => !skill.MetadataLifetime.IsFresh(this._timeProvider))).ConfigureAwait(false);

        this.RemoveObsoleteRefreshRequests();

        return skills;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;
            this._catalogCache.Clear();
            this._skillsToRefresh.Clear();
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
        if (!this._disposed && this._catalogCache.Contains(CatalogKey, skills => skills.Contains(skill)))
        {
            this._skillsToRefresh.TryAdd(skill, 0);
        }
    }

    /// <summary>
    /// Fetches the complete list if it is missing or expired, or refreshes queued and expired skills in a fresh list.
    /// </summary>
    private async ValueTask<McpCacheEntry<IList<AgentSkill>>> RefreshCatalogAsync(McpCacheEntry<IList<AgentSkill>>? cached, CancellationToken cancellationToken)
    {
        if (cached?.Lifetime.IsFresh(this._timeProvider) == true)
        {
            return await this.RefreshSkillsAsync(cached, cancellationToken).ConfigureAwait(false);
        }

        // Reloading all pages also updates queued skills, so there is no need to refresh them separately.
        return await this.FetchSkillsAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Queues expired skills and stores the updated list only if every queued refresh succeeds.
    /// </summary>
    /// <remarks>
    /// Replaces updated skills and removes missing ones in a new list, preserving the catalog's lifetime.
    /// If a fetch fails or is canceled, the previous list and pending requests remain available for retry.
    /// </remarks>
    private async Task<McpCacheEntry<IList<AgentSkill>>> RefreshSkillsAsync(McpCacheEntry<IList<AgentSkill>> cached, CancellationToken cancellationToken)
    {
        // Queue skills whose individual TTL has expired alongside those queued after a resource mismatch.
        // Skills loaded through listing use Infinite and are refreshed with the catalog instead.
        foreach (AgentMcpSkill skill in cached.Value.OfType<AgentMcpSkill>())
        {
            if (!skill.MetadataLifetime.IsFresh(this._timeProvider))
            {
                this._skillsToRefresh.TryAdd(skill, 0);
            }
        }

        List<AgentSkill>? updated = null;

        foreach (AgentMcpSkill skill in this._skillsToRefresh.Keys)
        {
            // Remove refresh requests for skill instances that are no longer in the cached catalog.
            if (!cached.Value.Contains(skill))
            {
                this._skillsToRefresh.TryRemove(skill, out _);
                continue;
            }

            AgentMcpSkill? replacement = await this.FetchSkillAsync(skill.Uri, cancellationToken).ConfigureAwait(false);
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
            return cached;
        }

        cancellationToken.ThrowIfCancellationRequested();

        // Commit only after every refresh succeeds; failures leave the catalog and pending work intact.
        return new(updated, cached.Lifetime);
    }

    /// <summary>
    /// Removes pending refresh requests for skill objects no longer in the published list.
    /// </summary>
    private void RemoveObsoleteRefreshRequests()
    {
        // Keep requests for skills still in the list: they may have been queued during the refresh
        // or just after the new catalog was stored.
        foreach (AgentMcpSkill skill in this._skillsToRefresh.Keys)
        {
            if (!this._catalogCache.Contains(CatalogKey, skills => skills.Contains(skill)))
            {
                this._skillsToRefresh.TryRemove(skill, out _);
            }
        }
    }

    /// <summary>
    /// Fetches the complete skill list with a lifetime ending at the earliest page expiration.
    /// </summary>
    private async Task<McpCacheEntry<IList<AgentSkill>>> FetchSkillsAsync(CancellationToken cancellationToken)
    {
        var (skillEntries, pageLifetimes) = await this.ListSkillEntriesAsync(cancellationToken).ConfigureAwait(false);

        List<AgentSkill> skills = [];

        foreach (McpSkillEntry entry in skillEntries)
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Listing responses specify a TTL per page, not per skill. Use Infinite to avoid independent
            // skill expiration; the page's TTL triggers a refresh of the whole catalog, including this skill.
            skills.Add(this.CreateSkill(entry, McpCacheLifetime.Infinite));
        }

        return new(skills, this.CombineLifetimes(pageLifetimes));
    }

    /// <summary>
    /// Fetches updated details for one skill and creates a replacement object, or returns null if the skill no longer exists.
    /// </summary>
    private async Task<AgentMcpSkill?> FetchSkillAsync(string skillUri, CancellationToken cancellationToken)
    {
        JsonRpcResponse response;
        try
        {
            response = await this._client.SendRequestAsync(new JsonRpcRequest
            {
                Method = "skills/get",
                Params = new JsonObject { ["uri"] = skillUri },
            }, cancellationToken).ConfigureAwait(false);
        }
        catch (McpProtocolException ex) when (ex.ErrorCode == McpErrorCode.InvalidParams || ex.ErrorCode == McpErrorCode.ResourceNotFound)
        {
            return null;
        }

        long receivedTimestamp = this._timeProvider.GetTimestamp();

        cancellationToken.ThrowIfCancellationRequested();

        McpSkillsGetResult result = response.Result?.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult)
            ?? throw new InvalidOperationException("The server returned no skills/get result.");

        if (result.ResultType != CompleteResultType)
        {
            throw new InvalidOperationException($"A skills/get result must have resultType '{CompleteResultType}'. Received resultType '{result.ResultType}'.");
        }

        if (!string.Equals(result.Skill.Uri, skillUri, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"The skills/get result must describe the requested skill '{skillUri}'.");
        }

        TimeSpan timeToLive = result.TimeToLive.GetValueOrDefault();
        if (timeToLive < TimeSpan.Zero)
        {
            timeToLive = TimeSpan.Zero;
        }

        // Unlike listing responses, skills/get provides a TTL for this skill,
        // allowing it to expire and refresh independently of the catalog.
        return this.CreateSkill(result.Skill, new McpCacheLifetime(receivedTimestamp, timeToLive));
    }

    /// <summary>
    /// Checks the server's skill details and creates a skill object with its own resource cache.
    /// </summary>
    private AgentMcpSkill CreateSkill(McpSkillEntry entry, McpCacheLifetime metadataLifetime)
    {
        AgentSkillFrontmatter frontmatter = CreateFrontmatter(entry);

        List<McpSkillResourceEntry> resources = this.CreateSupportingResources(entry);

        return new AgentMcpSkill(frontmatter, entry.Uri, resources, this._client, this, this._logger, this._maxResourceSizeBytes, this._timeProvider, metadataLifetime);
    }

    /// <summary>
    /// Creates one lifetime that ends when the earliest page expires.
    /// </summary>
    private McpCacheLifetime CombineLifetimes(List<McpCacheLifetime> lifetimes)
    {
        if (lifetimes.Count == 0)
        {
            throw new ArgumentException("At least one lifetime is required.", nameof(lifetimes));
        }

        long now = this._timeProvider.GetTimestamp();
        TimeSpan shortestRemaining = TimeSpan.MaxValue;

        // Compare all pages at the same timestamp; combining them must not extend the earliest expiration.
        foreach (McpCacheLifetime lifetime in lifetimes)
        {
            TimeSpan elapsed = this._timeProvider.GetElapsedTime(lifetime.ReceivedTimestamp, now);
            TimeSpan remaining = lifetime.TimeToLive <= elapsed ? TimeSpan.Zero : lifetime.TimeToLive - elapsed;

            if (remaining < shortestRemaining)
            {
                shortestRemaining = remaining;
            }
        }

        return new McpCacheLifetime(now, shortestRemaining);
    }

    /// <summary>
    /// Fetches all listing pages and records their lifetimes.
    /// </summary>
    /// <remarks>
    /// Invalid pages, repeated cursors, and exceeded limits fail the whole request.
    /// </remarks>
    private async Task<(List<McpSkillEntry> Entries, List<McpCacheLifetime> PageLifetimes)> ListSkillEntriesAsync(CancellationToken cancellationToken)
    {
        List<McpSkillEntry> skillEntries = [];
        List<McpCacheLifetime> pageLifetimes = [];
        HashSet<string> cursors = new(StringComparer.Ordinal);
        string? cursor = null;
        int pageCount = 0;

        do
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (pageCount >= this._maxPageCount)
            {
                throw new InvalidOperationException($"Skill discovery exceeds the maximum allowed page count ({this._maxPageCount}).");
            }

            JsonObject parameters = new();
            if (cursor is not null)
            {
                parameters["cursor"] = cursor;
            }

            JsonRpcResponse response = await this._client.SendRequestAsync(new JsonRpcRequest
            {
                Method = "skills/list",
                Params = parameters,
            }, cancellationToken).ConfigureAwait(false);

            long receivedTimestamp = this._timeProvider.GetTimestamp();
            pageCount++;

            cancellationToken.ThrowIfCancellationRequested();

            JsonNode resultNode = response.Result
                ?? throw new InvalidOperationException("The server returned no skills/list result.");

            // Reject excessive catalogs before deserializing their typed metadata or constructing skills.
            if (resultNode is JsonObject resultObject && resultObject["skills"] is JsonArray entries && entries.Count > this._maxSkillCount - skillEntries.Count)
            {
                throw new InvalidOperationException($"Skill discovery exceeds the maximum allowed skill count ({this._maxSkillCount}).");
            }

            McpSkillsListResult result = resultNode.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult)
                ?? throw new InvalidOperationException("The server returned no skills/list result.");

            if (result.ResultType != CompleteResultType)
            {
                throw new InvalidOperationException($"A skills/list result must have resultType '{CompleteResultType}'. Received resultType '{result.ResultType}'.");
            }

            TimeSpan pageTimeToLive = result.TimeToLive.GetValueOrDefault();
            if (pageTimeToLive < TimeSpan.Zero)
            {
                pageTimeToLive = TimeSpan.Zero;
            }

            pageLifetimes.Add(new McpCacheLifetime(receivedTimestamp, pageTimeToLive));

            cursor = result.NextCursor;
            if (cursor is not null && !cursors.Add(cursor))
            {
                throw new InvalidOperationException("The skills/list result contains a repeated pagination cursor.");
            }

            foreach (McpSkillEntry? entry in result.Skills)
            {
                // Nullable annotations do not reject null collection elements during deserialization.
                if (entry is null)
                {
                    throw new InvalidOperationException("The skills/list result contains a null skill entry.");
                }

                skillEntries.Add(entry);
            }
        }
        while (cursor is not null);

        return (skillEntries, pageLifetimes);
    }

    /// <summary>
    /// Validates the skill URI, name, and description and returns the metadata used to list the skill.
    /// </summary>
    private static AgentSkillFrontmatter CreateFrontmatter(McpSkillEntry entry)
    {
        // Instructions must be addressable as a safe, absolute resource, e.g. skill://unit-converter/SKILL.md.
        if (!Uri.TryCreate(entry.Uri, UriKind.Absolute, out _) ||
            !entry.Uri.EndsWith("/SKILL.md", StringComparison.Ordinal) ||
            entry.Uri.Contains('\\') || entry.Uri.Any(char.IsControl))
        {
            throw new InvalidOperationException("A skill entry must specify an absolute SKILL.md resource URI.");
        }

        // Validate the metadata needed to advertise the skill.
        if (!AgentSkillFrontmatter.ValidateName(entry.Frontmatter.Name, out string? reason) ||
            !AgentSkillFrontmatter.ValidateDescription(entry.Frontmatter.Description, out reason))
        {
            throw new InvalidOperationException($"Skill '{entry.Uri}' has invalid frontmatter: {reason}");
        }

        // skill://unit-converter/SKILL.md -> skill://unit-converter
        string directory = entry.Uri[..^"/SKILL.md".Length];

        // Start of "unit-converter" in skill://unit-converter; 0 if no '/'.
        int segmentStart = directory.LastIndexOf('/') + 1;

        // Opaque URI schemes can place the skill name directly after the scheme.
        if (segmentStart == 0)
        {
            // Start of "unit-converter" in skill:unit-converter.
            segmentStart = directory.IndexOf(':') + 1;
        }

        // directory[segmentStart..] extracts "unit-converter", which must match the advertised skill name.
        if (!string.Equals(directory[segmentStart..], entry.Frontmatter.Name, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Skill URI '{entry.Uri}' must end with its frontmatter name followed by /SKILL.md.");
        }

        // Project the fields used to advertise the skill.
        return new AgentSkillFrontmatter(entry.Frontmatter.Name, entry.Frontmatter.Description);
    }

    /// <summary>
    /// Checks the server's resource list, including the required <c>SKILL.md</c> entry.
    /// </summary>
    private List<McpSkillResourceEntry> CreateSupportingResources(McpSkillEntry entry)
    {
        string skillUri = entry.Uri;

        // skill://unit-converter/SKILL.md -> skill://unit-converter/ (keep the trailing slash).
        string skillRootUri = skillUri[..^"SKILL.md".Length];

        List<McpSkillResourceEntry> resources = [];
        HashSet<string> resourceUris = new(StringComparer.Ordinal);

        foreach (McpSkillResourceEntry? resource in entry.Resources)
        {
            this.ValidateResourceManifestEntry(resource, skillUri, skillRootUri);

            // Each resource URI must appear only once in the skill's resource list.
            if (!resourceUris.Add(resource.Uri))
            {
                throw new InvalidOperationException($"Skill '{skillUri}' contains a duplicate resource URI '{resource.Uri}'.");
            }

            resources.Add(resource);
        }

        if (!resourceUris.Contains(skillUri))
        {
            throw new InvalidOperationException($"Skill '{skillUri}' must include SKILL.md in its resource manifest.");
        }

        return resources;
    }

    /// <summary>
    /// Checks that a listed resource stays within the skill directory and has a valid content hash and size.
    /// </summary>
    private void ValidateResourceManifestEntry([NotNull] McpSkillResourceEntry? resource, string skillUri, string skillRootUri)
    {
        // Reject null entries, e.g. "resources": [null], which deserialization can accept.
        if (resource is null)
        {
            throw new InvalidOperationException($"Skill '{skillUri}' contains a null manifest entry.");
        }

        // Resources must stay under the skill root, e.g. skill://unit-converter/references/rates.md.
        if (!resource.Uri.StartsWith(skillRootUri, StringComparison.Ordinal) ||
            resource.Uri.Length == skillRootUri.Length ||
            !AgentMcpSkill.IsResourceNameSafe(resource.Uri[skillRootUri.Length..]))
        {
            throw new InvalidOperationException($"Skill '{skillUri}' contains an invalid resource manifest entry.");
        }

        if (!ResourceDigestRegex().IsMatch(resource.Digest))
        {
            throw new InvalidOperationException($"Resource '{resource.Uri}' must specify a digest as 'sha256:' followed by 64 lowercase hexadecimal characters.");
        }

        if (resource.Size < 0)
        {
            throw new InvalidOperationException($"Resource '{resource.Uri}' must specify a nonnegative size in bytes.");
        }

        if (resource.Size > this._maxResourceSizeBytes)
        {
            throw new InvalidOperationException($"Resource '{resource.Uri}' exceeds the maximum allowed size ({this._maxResourceSizeBytes} bytes).");
        }
    }

    /// <summary>
    /// Matches the required SHA-256 digest format.
    /// </summary>
    [GeneratedRegex(@"\Asha256:[0-9a-f]{64}\z", RegexOptions.CultureInvariant)]
    private static partial Regex ResourceDigestRegex();
}
