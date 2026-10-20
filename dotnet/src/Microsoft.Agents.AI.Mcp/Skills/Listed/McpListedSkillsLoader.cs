// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// Discovers skills through the MCP <c>skills/list</c> method.
/// </summary>
/// <remarks>
/// Instructions and resources are fetched later, when requested.
/// </remarks>
internal sealed partial class McpListedSkillsLoader : IDisposable
{
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
    private readonly SemaphoreSlim _discoveryGate = new(1, 1);
    private volatile CachedSkills? _cachedSkills;
    private bool _disposed;

    /// <summary>
    /// Initializes a loader for skills discovered through <c>skills/list</c>.
    /// </summary>
    /// <param name="client">The MCP client used to discover skills and fetch their content.</param>
    /// <param name="logger">Optional logger for frontmatter parsing diagnostics.</param>
    /// <param name="options">Optional discovery limits and size limit for listed resources.</param>
    /// <param name="timeProvider">Optional clock for checking page freshness.</param>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException">A configured limit is not positive.</exception>
    public McpListedSkillsLoader(McpClient client, ILogger? logger = null, AgentMcpSkillsSourceOptions? options = null, TimeProvider? timeProvider = null)
    {
        this._client = Throw.IfNull(client);
        this._logger = logger ?? NullLogger.Instance;
        this._maxResourceSizeBytes = options?.ListedResourceMaxSizeBytes ?? AgentMcpListedSkill.DefaultMaxResourceSizeBytes;
        this._maxPageCount = options?.ListedMaxPageCount ?? DefaultMaxPageCount;
        this._maxSkillCount = options?.ListedMaxSkillCount ?? DefaultMaxSkillCount;
        this._timeProvider = timeProvider ?? TimeProvider.System;
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxResourceSizeBytes, nameof(options.ListedResourceMaxSizeBytes));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxPageCount, nameof(options.ListedMaxPageCount));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxSkillCount, nameof(options.ListedMaxSkillCount));
    }

    /// <summary>
    /// Gets the server's listed skills across all pages without fetching their instructions or resources.
    /// </summary>
    /// <param name="cancellationToken">The token used to cancel discovery.</param>
    /// <returns>The skills discovered through <c>skills/list</c>.</returns>
    /// <exception cref="JsonException">The response cannot be deserialized into a skill list.</exception>
    /// <exception cref="InvalidOperationException">The response is missing or contains an unsupported result type,
    /// invalid skill metadata or resource manifests, a repeated pagination cursor, or a configured limit is exceeded.</exception>
    /// <exception cref="McpException">The MCP request fails.</exception>
    /// <exception cref="OperationCanceledException">Discovery is canceled.</exception>
    /// <exception cref="ObjectDisposedException">The loader has been disposed.</exception>
    public async Task<IList<AgentSkill>> DiscoverAsync(CancellationToken cancellationToken)
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
            var (skills, pageLifetimes) = await this.DiscoverCoreAsync(cancellationToken).ConfigureAwait(false);

            cancellationToken.ThrowIfCancellationRequested();

            this.CacheSkills(skills, pageLifetimes);

            return skills;
        }
        finally
        {
            this._discoveryGate.Release();
        }
    }

    private async Task<(List<AgentSkill> Skills, List<PageLifetime> PageLifetimes)> DiscoverCoreAsync(CancellationToken cancellationToken)
    {
        var (skillEntries, pageLifetimes) = await this.ListSkillEntriesAsync(cancellationToken).ConfigureAwait(false);

        List<AgentSkill> skills = [];

        foreach (McpListedSkillEntry entry in skillEntries)
        {
            cancellationToken.ThrowIfCancellationRequested();

            AgentSkillFrontmatter frontmatter = CreateFrontmatter(entry);
            List<McpListedSkillResourceEntry> resources = this.CreateSupportingResources(entry);

            skills.Add(new AgentMcpListedSkill(frontmatter, entry.Uri, resources, this._client, this._logger, this._maxResourceSizeBytes));
        }

        return (skills, pageLifetimes);
    }

    private async Task<(List<McpListedSkillEntry> Entries, List<PageLifetime> PageLifetimes)> ListSkillEntriesAsync(CancellationToken cancellationToken)
    {
        List<McpListedSkillEntry> skillEntries = [];
        List<PageLifetime> pageLifetimes = [];
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

            McpSkillsListResult result = resultNode.Deserialize(McpListedSkillsJsonContext.Default.McpSkillsListResult)
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

            pageLifetimes.Add(new PageLifetime(receivedTimestamp, pageTimeToLive));

            cursor = result.NextCursor;
            if (cursor is not null && !cursors.Add(cursor))
            {
                throw new InvalidOperationException("The skills/list result contains a repeated pagination cursor.");
            }

            foreach (McpListedSkillEntry? entry in result.Skills)
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
        foreach (PageLifetime page in cached.PageLifetimes)
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
    /// <param name="skills">The complete list of discovered and validated skills.</param>
    /// <param name="pageLifetimes">The receipt timestamp and TTL of each discovery page.</param>
    private void CacheSkills(List<AgentSkill> skills, List<PageLifetime> pageLifetimes)
    {
        // Publish the complete catalog and page lifetimes together only after discovery and validation succeed.
        this._cachedSkills = new CachedSkills(skills, pageLifetimes);
    }

    private static AgentSkillFrontmatter CreateFrontmatter(McpListedSkillEntry entry)
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
    /// Validates and returns all resources listed for the skill, including <c>SKILL.md</c>, which contains
    /// the skill's instructions.
    /// </summary>
    private List<McpListedSkillResourceEntry> CreateSupportingResources(McpListedSkillEntry entry)
    {
        string skillUri = entry.Uri;

        // skill://unit-converter/SKILL.md -> skill://unit-converter/ (keep the trailing slash).
        string skillRootUri = skillUri[..^"SKILL.md".Length];

        List<McpListedSkillResourceEntry> resources = [];
        HashSet<string> resourceUris = new(StringComparer.Ordinal);

        foreach (McpListedSkillResourceEntry? resource in entry.Resources)
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

    private void ValidateResourceManifestEntry([NotNull] McpListedSkillResourceEntry? resource, string skillUri, string skillRootUri)
    {
        // Reject null entries, e.g. "resources": [null], which deserialization can accept.
        if (resource is null)
        {
            throw new InvalidOperationException($"Skill '{skillUri}' contains a null manifest entry.");
        }

        // Resources must stay under the skill root, e.g. skill://unit-converter/references/rates.md.
        if (!resource.Uri.StartsWith(skillRootUri, StringComparison.Ordinal) ||
            resource.Uri.Length == skillRootUri.Length ||
            !AgentMcpListedSkill.IsResourceNameSafe(resource.Uri[skillRootUri.Length..]))
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

    [GeneratedRegex(@"\Asha256:[0-9a-f]{64}\z", RegexOptions.CultureInvariant)]
    private static partial Regex ResourceDigestRegex();

    private sealed record CachedSkills(List<AgentSkill> Skills, List<PageLifetime> PageLifetimes);

    private sealed record PageLifetime(long ReceivedTimestamp, TimeSpan TimeToLive);

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
