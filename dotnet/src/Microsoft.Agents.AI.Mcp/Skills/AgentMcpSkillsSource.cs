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
/// Lists skills from an MCP server and provides access to their <c>SKILL.md</c> files and supporting resources.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="GetSkillsAsync"/> requests the available skills through <c>skills/list</c>.
/// The server must declare the <c>io.modelcontextprotocol/skills</c> extension;
/// otherwise, this source returns an empty list without sending a request.
/// Each listed skill includes a name, description, and resource list with expected byte sizes and content hashes.
/// This resource list is called the manifest and includes <c>SKILL.md</c>, which contains the skill's instructions.
/// </para>
/// <para>
/// The skill list may span multiple response pages, each with a time to live (TTL).
/// The list is cached until any page expires, then fetched again on the next <see cref="GetSkillsAsync"/> call.
/// By default, a missing, zero, or negative page TTL causes the list to be fetched on every call.
/// Configure <see cref="AgentMcpSkillsSourceOptions.TtlResolver"/> to override page and resource TTLs.
/// Disable other caches around this source, including the builder's cache through
/// <see cref="AgentSkillsProviderBuilder.DisableCaching"/>, so this source can check expiration on each call.
/// </para>
/// <para>
/// Listing a skill does not fetch its files. The returned skill object fetches <c>SKILL.md</c>
/// and supporting resources only when their content is requested. Only resources in its manifest are available.
/// Each resource response must contain one text or binary content block; <c>SKILL.md</c> must contain text.
/// Fetched content is checked against the resource's expected size and content hash.
/// The name and description at the start of <c>SKILL.md</c> must also match the listed skill.
/// </para>
/// <para>
/// Each skill object caches resource content separately from the skill list, using each resource response's TTL.
/// Expired resource content is fetched again on access. By default, a missing, zero, or negative resource TTL
/// causes content to be fetched on every access. All TTLs start when responses arrive, before validation.
/// </para>
/// <para>
/// If fetched resource content has a different size or content hash than its manifest entry,
/// the skill that owns that resource is queued for refresh.
/// The resource read returns previously verified cached content if available, without extending its TTL;
/// otherwise, it throws. Other resource-read and validation errors propagate without queuing a skill refresh.
/// </para>
/// <para>
/// On the next <see cref="GetSkillsAsync"/> call, <c>skills/get</c> fetches updated metadata and resource lists
/// for queued skills. Skills that no longer exist on the server are removed from the cached list.
/// If the cached skill list has expired, <c>skills/list</c> fetches the whole list instead.
/// A failed refresh leaves the previous list unchanged and is retried on a later call.
/// </para>
/// <para>
/// Refreshes return a new list with new objects for updated skills. Previously returned skill objects
/// continue using the resource URIs, sizes, and content hashes they were created with.
/// Previously returned content stays unchanged. Callers must load the new skill object to use an update.
/// Refreshes happen only on request, not in the background.
/// </para>
/// <para>
/// <see cref="AgentMcpSkillsSourceOptions"/> limits listing pages, skill counts, and resource sizes.
/// Invalid pages, repeated cursors, and exceeded limits fail the request rather than returning a partial list.
/// These limits do not bound incoming message size or total memory use. Configure input-size limits
/// in the MCP client, transport, or host as needed.
/// </para>
/// <para>
/// Supporting-resource names must stay within the skill's directory.
/// Resource URIs are sent to the connected MCP server, not opened locally.
/// These checks do not replace server-side authorization.
/// </para>
/// <para>
/// The caller owns the MCP client. Disposing this source does not dispose the client;
/// previously returned skills can continue reading resources while that client remains usable.
/// </para>
/// <para>
/// <strong>Security:</strong> Remote skills are loaded only when this source is explicitly configured.
/// Only connect to servers you trust and treat their content as untrusted input.
/// Malicious instructions or scripts can manipulate the agent or expose data.
/// A matching content hash does not prove that content is safe: the server supplies both the hash and the content.
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
    private readonly Func<TimeSpan?, TimeSpan>? _ttlResolver;
    private readonly McpSkillsLoader _skillsLoader;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional TTL resolver and limits for listing pages, skill counts, and resource sizes.</param>
    /// <param name="loggerFactory">Optional factory for diagnostic logging.</param>
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
        this._ttlResolver = options?.TtlResolver;
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxResourceSizeBytes, nameof(options.ListedResourceMaxSizeBytes));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxPageCount, nameof(options.ListedMaxPageCount));
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(this._maxSkillCount, nameof(options.ListedMaxSkillCount));
        this._skillsLoader = new McpSkillsLoader(this._timeProvider, this.FetchSkillsAsync, this.FetchSkillAsync);
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

        IList<AgentSkill> skills = await this._skillsLoader.GetSkillsAsync(cancellationToken).ConfigureAwait(false);

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._skillsLoader.Dispose();
        }

        base.Dispose(disposing);
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

            skills.Add(this.CreateSkill(entry));
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

        return this.CreateSkill(result.Skill);
    }

    /// <summary>
    /// Checks the server's skill details and creates a skill object with its own resource cache.
    /// </summary>
    private AgentMcpSkill CreateSkill(McpSkillEntry entry)
    {
        AgentSkillFrontmatter frontmatter = CreateFrontmatter(entry);

        List<McpSkillResourceEntry> resources = this.CreateSupportingResources(entry);

        return new AgentMcpSkill(frontmatter, entry.Uri, resources, this._client, this._skillsLoader, this._logger, this._maxResourceSizeBytes, this._timeProvider, this._ttlResolver);
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

            pageLifetimes.Add(McpCacheLifetime.Create(receivedTimestamp, result.TimeToLive, this._ttlResolver));

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

    /// <summary>
    /// Reports how many skills the source returned.
    /// </summary>
    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    /// <summary>
    /// Logs that the server does not declare support for skills.
    /// </summary>
    [LoggerMessage(LogLevel.Debug, "No io.modelcontextprotocol/skills extension declared by MCP server; skill discovery is skipped.")]
    private static partial void LogSkillsExtensionAbsent(ILogger logger);
}
