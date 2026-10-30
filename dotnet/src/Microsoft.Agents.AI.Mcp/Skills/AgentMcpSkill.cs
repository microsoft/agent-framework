// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Buffers.Text;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents an MCP skill and loads its <c>SKILL.md</c> file and supporting resources on request.
/// </summary>
/// <remarks>
/// <para>
/// The server provides a resource list (manifest) with each resource's URI, expected size, and content hash.
/// This skill uses that list to check which resources can be read and whether their content has changed.
/// The name and description at the start of <c>SKILL.md</c> (frontmatter) must also match the server's listing.
/// </para>
/// <para>
/// Each resource is cached until its time to live (TTL) expires, then fetched again.
/// If a resource's size or content hash has changed, a skill refresh is queued.
/// Previously verified content, if available, is returned and cached indefinitely for this skill object
/// to avoid unnecessary requests for a resource that no longer matches its manifest.
/// If no verified content is cached when a mismatch occurs, the read throws. Other errors propagate.
/// </para>
/// <para>
/// A refresh creates a new skill object with the server's updated resource list.
/// Existing skill objects continue checking reads against the resource list they were created with.
/// The catalog uses <see cref="MetadataLifetime"/> to refresh skill metadata independently of resource content.
/// </para>
/// </remarks>
internal sealed partial class AgentMcpSkill : AgentSkill
{
    internal const long DefaultMaxResourceSizeBytes = 1024 * 1024;

    private const int MaxResourceNameDecodingDepth = 32;

    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly string _skillRootUri;
    private readonly IReadOnlyList<McpSkillResourceEntry> _resources;
    private readonly long _maxResourceSizeBytes;
    private readonly McpSkillsCatalog _skillsCatalog;
    private readonly TimeProvider _timeProvider;
    private readonly McpCache<string, ResourceContents> _resourceCache;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkill"/> class.
    /// </summary>
    /// <param name="frontmatter">The skill's name and description.</param>
    /// <param name="uri">The resource URI of the skill's <c>SKILL.md</c>.</param>
    /// <param name="resources">The allowed resource URIs and their expected sizes and content hashes, including <c>SKILL.md</c>.</param>
    /// <param name="client">The MCP client used to fetch <c>SKILL.md</c> and supporting resources.</param>
    /// <param name="catalog">The catalog to notify when a content mismatch requires updated skill details.</param>
    /// <param name="logger">Optional logger for validation diagnostics.</param>
    /// <param name="maxResourceSizeBytes">The maximum allowed resource size in bytes.</param>
    /// <param name="timeProvider">Optional clock for resource expiration.</param>
    /// <param name="metadataLifetime">Optional lifetime for skill metadata. Defaults to no independent expiration; the catalog lifetime controls refreshes.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="maxResourceSizeBytes"/> is not positive.</exception>
    public AgentMcpSkill(AgentSkillFrontmatter frontmatter, string uri, IReadOnlyList<McpSkillResourceEntry> resources, McpClient client, McpSkillsCatalog catalog, ILogger? logger = null, long maxResourceSizeBytes = DefaultMaxResourceSizeBytes, TimeProvider? timeProvider = null, McpCacheLifetime? metadataLifetime = null)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this.Uri = Throw.IfNullOrWhitespace(uri);
        this.MetadataLifetime = metadataLifetime ?? McpCacheLifetime.Infinite;
        this._skillRootUri = this.Uri[..^"SKILL.md".Length];
        this._resources = Throw.IfNull(resources);
        this._client = Throw.IfNull(client);
        this._skillsCatalog = Throw.IfNull(catalog);
        this._timeProvider = timeProvider ?? TimeProvider.System;
        this._resourceCache = new(this._timeProvider, StringComparer.Ordinal);
        this._logger = logger ?? NullLogger.Instance;
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxResourceSizeBytes);
        this._maxResourceSizeBytes = maxResourceSizeBytes;
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <summary>
    /// Gets the resource URI of the skill's <c>SKILL.md</c> file.
    /// </summary>
    internal string Uri { get; }

    /// <summary>
    /// Gets the skill lifetime.
    /// </summary>
    internal McpCacheLifetime MetadataLifetime { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Returns the text of <c>SKILL.md</c>, using cached content until it expires.
    /// Fetched content is checked against the expected size, content hash, name, and description.
    /// A size or content hash mismatch returns previously verified content if available and queues a skill refresh.
    /// </remarks>
    /// <exception cref="InvalidOperationException">The <c>SKILL.md</c> resource is missing or invalid,
    /// exceeds the size limit, has a different name or description, or fails the size or content hash check without cached content to return.</exception>
    public override async ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
    {
        McpSkillResourceEntry? skillMdResource = this._resources.FirstOrDefault(resource => string.Equals(resource.Uri, this.Uri, StringComparison.Ordinal));
        if (skillMdResource is null)
        {
            throw new InvalidOperationException($"The resource list must include the skill's SKILL.md resource '{this.Uri}'.");
        }

        ResourceContents content = await this.GetResourceContentAsync(skillMdResource, cancellationToken).ConfigureAwait(false);

        if (content is not TextResourceContents textContent)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this.Uri}'.");
        }

        return textContent.Text;
    }

    /// <inheritdoc/>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="name"/> is empty or whitespace-only.</exception>
    /// <remarks>
    /// Returns a supporting resource from the server's resource list, using cached content until it expires.
    /// Returns <see langword="null"/> for unsafe names, unlisted resources, or <c>SKILL.md</c>.
    /// A size or content hash mismatch returns previously verified content if available and queues a skill refresh.
    /// </remarks>
    /// <exception cref="InvalidOperationException">The resource response is invalid, exceeds the size limit,
    /// or fails the size or content hash check without cached content to return.</exception>
    public override async ValueTask<AgentSkillResource?> GetResourceAsync(string name, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(name);

        string normalized = name.Replace('\\', '/');

        // Reject paths that could escape the skill before sending a request.
        if (!IsResourceNameSafe(normalized))
        {
            return null;
        }

        string uri = this._skillRootUri + normalized;

        // Exclude SKILL.md, which should be loaded via GetContentAsync.
        if (string.Equals(uri, this.Uri, StringComparison.Ordinal))
        {
            return null;
        }

        // Supporting reads must stay within the held manifest.
        McpSkillResourceEntry? resource = this._resources.FirstOrDefault(resource => string.Equals(resource.Uri, uri, StringComparison.Ordinal));
        if (resource is null)
        {
            return null;
        }

        ResourceContents content = await this.GetResourceContentAsync(resource, cancellationToken).ConfigureAwait(false);

        return new AgentMcpSkillResource(name, content);
    }

    /// <summary>
    /// Gets resource content checked against the size and content hash recorded when this skill was created.
    /// </summary>
    /// <remarks>
    /// Reads of the same resource wait for earlier reads to finish.
    /// A size or content hash mismatch queues a skill refresh and returns previously verified content when available.
    /// </remarks>
    private ValueTask<ResourceContents> GetResourceContentAsync(McpSkillResourceEntry resource, CancellationToken cancellationToken)
    {
        return this._resourceCache.GetOrRefreshAsync(
            resource.Uri,
            (cached, token) => this.FetchResourceContentAsync(resource, cached, token),
            cancellationToken);
    }

    /// <summary>
    /// Fetches and validates resource content, returning previously verified content on a size or content hash mismatch when available.
    /// </summary>
    private async ValueTask<McpCacheEntry<ResourceContents>> FetchResourceContentAsync(McpSkillResourceEntry resource, McpCacheEntry<ResourceContents>? cached, CancellationToken cancellationToken)
    {
#pragma warning disable CA2234 // Preserve the exact resource URI advertised by the server.
        ReadResourceResult response = await this._client.ReadResourceAsync(resource.Uri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234

        // Validation time consumes the TTL; network request time does not.
        long receivedTimestamp = this._timeProvider.GetTimestamp();

        ResourceContents content = this.GetValidatedResourceContent(resource, response);
        if (!this.TryVerifyResourceIntegrity(resource, content, out string? mismatch))
        {
            cancellationToken.ThrowIfCancellationRequested();

            // The resource may have changed; request a new manifest without changing this skill's held manifest.
            this._skillsCatalog.QueueSkillRefresh(this);
            LogResourceIntegrityMismatch(this._logger, resource.Uri, this.Uri, mismatch);
            cancellationToken.ThrowIfCancellationRequested();

            if (cached is null)
            {
                throw new InvalidOperationException($"Resource '{resource.Uri}' has a {mismatch} that differs from the resource manifest.");
            }

            // When the resource's size or digest changes, the cached content becomes stale but still matches this skill's held manifest.
            // A skill refresh is queued, so keep the cached content indefinitely to avoid fetching the changed resource again.
            // A refresh creates a new skill object with the updated manifest and a separate resource cache.
            return new(cached.Value, McpCacheLifetime.Infinite);
        }

        // Only the skill's SKILL.md must have frontmatter matching the listed name and description.
        if (string.Equals(resource.Uri, this.Uri, StringComparison.Ordinal))
        {
            this.VerifyInstructions(content);
        }

        return new(content, new(receivedTimestamp, response.TimeToLive.GetValueOrDefault()));
    }

    /// <summary>
    /// Gets and validates the response's single text or binary content block.
    /// </summary>
    /// <remarks>
    /// <c>SKILL.md</c> must contain text. Binary content is decoded and checked against the size limit.
    /// </remarks>
    private ResourceContents GetValidatedResourceContent(McpSkillResourceEntry resource, ReadResourceResult result)
    {
        string uri = resource.Uri;
        if (result.Contents.Count == 0)
        {
            throw new InvalidOperationException($"The MCP server returned no content for resource '{uri}'.");
        }

        if (result.Contents.Count > 1)
        {
            throw new InvalidOperationException($"Resource '{uri}' must contain exactly one text or binary content block; the MCP server returned {result.Contents.Count}.");
        }

        ResourceContents content = result.Contents[0];

        if (content is not (TextResourceContents or BlobResourceContents))
        {
            throw new InvalidOperationException($"The MCP server returned unsupported content for resource '{uri}'.");
        }

        // SKILL.md contains the skill's instructions and must be returned as text.
        if (string.Equals(uri, this.Uri, StringComparison.Ordinal) && content is not TextResourceContents)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this.Uri}'.");
        }

        return content is BlobResourceContents binary ? this.DecodeBinaryContent(binary, uri) : content;
    }

    /// <summary>
    /// Checks the content against the server's expected size and content hash and reports any mismatch.
    /// </summary>
    private bool TryVerifyResourceIntegrity(McpSkillResourceEntry resource, ResourceContents content, [NotNullWhen(false)] out string? mismatch)
    {
        int byteSize;

        switch (content)
        {
            case TextResourceContents text:
            {
                // Character count is a lower bound that avoids overflowing GetByteCount for huge strings.
                this.ValidateResourceSize(resource.Uri, text.Text.Length);

                byteSize = Encoding.UTF8.GetByteCount(text.Text);

                this.ValidateResourceSize(resource.Uri, byteSize);

                break;
            }
            case BlobResourceContents blob:
            {
                // Base64 validity and the decoded size limit were already checked by DecodeBinaryContent
                // when GetValidatedResourceContent loaded the binary content.
                byteSize = blob.DecodedData.Length;

                break;
            }

            default:
                throw new InvalidOperationException($"The MCP server returned unsupported content for resource '{resource.Uri}'.");
        }

        // Reject a size mismatch before encoding text or hashing decoded binary content.
        if (byteSize != resource.Size)
        {
            mismatch = "byte size";
            return false;
        }

        ReadOnlyMemory<byte> bytes = content switch
        {
            TextResourceContents text => Encoding.UTF8.GetBytes(text.Text),
            BlobResourceContents binary => binary.DecodedData,
            _ => throw new InvalidOperationException("Unsupported listed skill content."),
        };

        string digest = Convert.ToHexString(SHA256.HashData(bytes.Span));

        // Content can change without changing size.
        if (!digest.AsSpan().Equals(resource.Digest.AsSpan("sha256:".Length), StringComparison.OrdinalIgnoreCase))
        {
            mismatch = "SHA-256 digest";
            return false;
        }

        mismatch = null;
        return true;
    }

    /// <summary>
    /// Checks that <c>SKILL.md</c> contains text with the name and description advertised for this skill.
    /// </summary>
    private void VerifyInstructions(ResourceContents content)
    {
        if (content is not TextResourceContents textContent)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this.Uri}'.");
        }

        if (!AgentSkillFrontmatterParser.TryParse(textContent.Text, this.Uri, this._logger, out AgentSkillFrontmatter? frontmatter))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this.Uri}' contains invalid frontmatter.");
        }

        if (!string.Equals(frontmatter.Name, this.Frontmatter.Name, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this.Uri}' has a frontmatter name that differs from the skills/list entry.");
        }

        if (!string.Equals(frontmatter.Description, this.Frontmatter.Description, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this.Uri}' has a frontmatter description that differs from the skills/list entry.");
        }
    }

    /// <summary>
    /// Logs a resource mismatch and the queued skill refresh.
    /// </summary>
    [LoggerMessage(LogLevel.Warning, "Resource '{ResourceUri}' has a {Mismatch} that differs from the resource manifest for skill '{SkillUri}'. A skill refresh has been queued.")]
    private static partial void LogResourceIntegrityMismatch(ILogger logger, string resourceUri, string skillUri, string mismatch);

    /// <summary>
    /// Decodes binary content and checks its size.
    /// </summary>
    /// <param name="content">The Base64-encoded resource content.</param>
    /// <param name="uri">The resource URI used in error messages.</param>
    /// <returns>Decoded content with the original resource metadata.</returns>
    /// <exception cref="InvalidOperationException">The Base64 content is invalid or its decoded size exceeds the configured limit.</exception>
    private BlobResourceContents DecodeBinaryContent(BlobResourceContents content, string uri)
    {
        ReadOnlySpan<byte> encoded = content.Blob.Span;

        if (!Base64.IsValid(encoded, out int byteSize))
        {
            throw new InvalidOperationException($"Resource '{uri}' contains invalid base64 content.");
        }

        this.ValidateResourceSize(uri, byteSize);

        byte[] bytes = new byte[byteSize];
        Span<byte> block = stackalloc byte[256];
        int bytesWritten = 0;

        // Decode whitespace-free blocks of complete Base64 quartets so capacity checks use only Base64 data.
        for (int offset = 0; offset < encoded.Length;)
        {
            int blockLength = 0;
            while (offset < encoded.Length && blockLength < block.Length)
            {
                byte value = encoded[offset++];
                if (value is not ((byte)' ' or (byte)'\t' or (byte)'\r' or (byte)'\n'))
                {
                    block[blockLength++] = value;
                }
            }

            if (Base64.DecodeFromUtf8(block[..blockLength], bytes.AsSpan(bytesWritten), out _, out int written) != OperationStatus.Done)
            {
                throw new InvalidOperationException($"Resource '{uri}' contains invalid base64 content.");
            }

            bytesWritten += written;
        }

        if (bytesWritten != byteSize)
        {
            throw new InvalidOperationException($"Resource '{uri}' contains invalid base64 content.");
        }

        BlobResourceContents decodedContent = BlobResourceContents.FromBytes(bytes, content.Uri, content.MimeType);
        decodedContent.Meta = content.Meta;
        return decodedContent;
    }

    /// <summary>
    /// Rejects content larger than the configured byte limit.
    /// </summary>
    private void ValidateResourceSize(string uri, long size)
    {
        if (size > this._maxResourceSizeBytes)
        {
            throw new InvalidOperationException($"Resource '{uri}' exceeds the maximum allowed size ({this._maxResourceSizeBytes} bytes).");
        }
    }

    /// <summary>
    /// Checks that a relative resource name stays within the skill's directory.
    /// </summary>
    internal static bool IsResourceNameSafe(string normalized)
    {
        // Separate the file path from query (?...) or fragment (#...) text before decoding.
        // Example: guide.md?version=1 becomes path "guide.md" and suffix "version=1".
        string[] parts = normalized.Split(['?', '#'], 2);

        // Decode encoded characters to reveal attempts to leave the skill directory.
        // Example: %252e%252e/secret.txt becomes ../secret.txt.
        string? path = FullyUnescape(parts[0]);

        // Decode query/fragment text too: value=%00 contains an invisible control character after decoding.
        string? suffix = FullyUnescape(parts.Length > 1 ? parts[1] : string.Empty);

        // Allow relative paths such as references/guide.md, but reject /etc/passwd,
        // https://example.com/file, and ../secret.txt. Neither the path nor the suffix may contain control characters.
        return path is not null && suffix is not null
            && !path.StartsWith('/')
            && !path.Contains("://", StringComparison.Ordinal)
            && !path.Split(['/', '?', '#']).Any(segment => string.Equals(segment.TrimEnd(' '), "..", StringComparison.Ordinal))
            && !(path + suffix).Any(char.IsControl);
    }

    /// <summary>
    /// Removes nested path escapes so resource-name checks can detect unsafe paths.
    /// </summary>
    /// <returns>The decoded value, or null if too many decoding steps are needed.</returns>
    private static string? FullyUnescape(string value)
    {
        // Bound decoding work while still checking that the final pass has stabilized.
        for (int depth = 0; depth <= MaxResourceNameDecodingDepth; depth++)
        {
            string decoded = System.Uri.UnescapeDataString(value).Replace('\\', '/');

            // The stable form exposes traversal and control characters hidden by nested encoding.
            if (decoded == value)
            {
                return value;
            }

            value = decoded;
        }

        return null;
    }
}
