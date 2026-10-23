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
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkillsSource"/> that discovers Agent Skills served over the Model Context Protocol (MCP).
/// </summary>
/// <remarks>
/// <para>
/// Uses <c>skills/list</c> when the server declares the <c>io.modelcontextprotocol/skills</c> extension.
/// Returns an empty skill list without sending a discovery request when the extension is not declared.
/// </para>
/// <para>
/// Listed skill discovery is based on the Skills extension specification incorporating the
/// working group's decision dated <c>2026-09-08</c>.
/// Support currently includes skill discovery through <c>skills/list</c> and reading listed skill resources,
/// but not the full extension.
/// </para>
/// <para>
/// Listed skills provide a name, description, and list of resources. Instructions and supporting resources
/// are fetched from the MCP server when requested. Only supporting resources listed by the server are available.
/// Each listed resource read must return exactly one text or binary content block; <c>SKILL.md</c> must contain text.
/// Page counts, total skill counts, and individual resource sizes
/// are bounded by <see cref="AgentMcpSkillsSourceOptions"/>. Discovery follows continuation cursors
/// until exhausted and fails on repeated cursors, invalid pages, or exceeded limits instead of returning a partial catalog.
/// These checks do not limit incoming messages before the supplied client receives and parses them.
/// </para>
/// <para>
/// Skills discovered through <c>skills/list</c> are cached according to server-provided TTLs.
/// When any page expires, the skills are refreshed on the next request.
/// If any page has no TTL, the skill list is requested from the server on every call.
/// To honor these TTLs, disable any additional caching layers around this source,
/// including the builder's cache by calling <see cref="AgentSkillsProviderBuilder.DisableCaching"/>.
/// </para>
/// <para>
/// Supporting resource names are checked for absolute paths, parent traversal (including
/// percent-encoded forms), and control characters before an MCP request is sent. Resource URIs
/// retain their MCP resource schemes: they are sent to the connected server, not opened locally.
/// This client-side guard does not replace server-side authorization.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> This source discovers and loads skills — including full
/// skill instructions and supporting resources — from a
/// remote MCP server that the caller connects to explicitly (via <c>UseMcpSkills</c>); it is never
/// enabled by default. A compromised, malicious, or simply untrustworthy MCP server can return
/// adversarial skill content designed to manipulate the agent through indirect prompt injection, or
/// instructions/scripts designed to exfiltrate data once loaded and, for script-capable skills,
/// executed. Only connect this source to MCP servers you trust, and review discovery and resource limits (<see cref="AgentMcpSkillsSourceOptions"/>)
/// to bound the impact of a malicious server. A matching digest proves consistency with the resource manifest,
/// not trustworthiness: a server controlling both the manifest and resource can replace both.
/// </para>
/// <para>
/// This source does not impose a byte limit on individual or combined <c>skills/list</c> responses.
/// Page-count, skill-count, and resource-size limits do not bound incoming message size or total
/// memory consumption. A malicious, compromised, or misconfigured server can return oversized
/// responses that cause excessive memory consumption. Application developers are responsible for
/// configuring appropriate input-size and resource limits through their chosen MCP client, transport,
/// or hosting environment.
/// </para>
/// </remarks>
public sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    private const string SkillsExtensionName = "io.modelcontextprotocol/skills";
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
    private readonly McpSkillsCache _cache;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional options that control skill loading.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException">A configured limit is not positive.</exception>
    public AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options = null, ILoggerFactory? loggerFactory = null)
        : this(client, options, loggerFactory, TimeProvider.System)
    {
    }

    internal AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options, ILoggerFactory? loggerFactory, TimeProvider timeProvider)
    {
        this._client = Throw.IfNull(client);
        loggerFactory ??= NullLoggerFactory.Instance;
        this._logger = loggerFactory.CreateLogger<AgentMcpSkillsSource>();
        this._maxResourceSizeBytes = options?.ListedResourceMaxSizeBytes ?? AgentMcpSkill.DefaultMaxResourceSizeBytes;
        this._maxPageCount = options?.ListedMaxPageCount ?? DefaultMaxPageCount;
        this._maxSkillCount = options?.ListedMaxSkillCount ?? DefaultMaxSkillCount;
        this._timeProvider = Throw.IfNull(timeProvider);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxResourceSizeBytes, nameof(options.ListedResourceMaxSizeBytes));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxPageCount, nameof(options.ListedMaxPageCount));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxSkillCount, nameof(options.ListedMaxSkillCount));
        this._cache = new McpSkillsCache(this._timeProvider, this.DiscoverCoreAsync);
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)Mcp.FeatureIndex.CoreMcpSkillsSource);
#pragma warning restore MAAI001

        cancellationToken.ThrowIfCancellationRequested();

        if (this._client.ServerCapabilities.Extensions?.ContainsKey(SkillsExtensionName) != true)
        {
            LogSkillsExtensionAbsent(this._logger);
            return [];
        }

        IList<AgentSkill> skills = await this._cache.GetOrCreateAsync(cancellationToken).ConfigureAwait(false);

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._cache.Dispose();
        }

        base.Dispose(disposing);
    }

    private async Task<McpSkillsSnapshot> DiscoverCoreAsync(CancellationToken cancellationToken)
    {
        var (skillEntries, pageLifetimes) = await this.ListSkillEntriesAsync(cancellationToken).ConfigureAwait(false);

        List<AgentSkill> skills = [];

        foreach (McpSkillEntry entry in skillEntries)
        {
            cancellationToken.ThrowIfCancellationRequested();

            AgentSkillFrontmatter frontmatter = CreateFrontmatter(entry);
            List<McpSkillResourceEntry> resources = this.CreateSupportingResources(entry);

            skills.Add(new AgentMcpSkill(frontmatter, entry.Uri, resources, this._client, this._logger, this._maxResourceSizeBytes));
        }

        return new McpSkillsSnapshot(skills, pageLifetimes);
    }

    private async Task<(List<McpSkillEntry> Entries, List<McpSkillsPageLifetime> PageLifetimes)> ListSkillEntriesAsync(CancellationToken cancellationToken)
    {
        List<McpSkillEntry> skillEntries = [];
        List<McpSkillsPageLifetime> pageLifetimes = [];
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

            pageLifetimes.Add(new McpSkillsPageLifetime(receivedTimestamp, pageTimeToLive));

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
    /// Validates and returns all resources listed for the skill, including <c>SKILL.md</c>, which contains
    /// the skill's instructions.
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

    [GeneratedRegex(@"\Asha256:[0-9a-f]{64}\z", RegexOptions.CultureInvariant)]
    private static partial Regex ResourceDigestRegex();

    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    [LoggerMessage(LogLevel.Debug, "No io.modelcontextprotocol/skills extension declared by MCP server; skill discovery is skipped.")]
    private static partial void LogSkillsExtensionAbsent(ILogger logger);
}
