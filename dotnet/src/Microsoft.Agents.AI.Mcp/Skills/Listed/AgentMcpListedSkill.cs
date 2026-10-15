// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Buffers.Text;
using System.Collections.Generic;
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
/// A skill discovered through <c>skills/list</c>.
/// </summary>
/// <remarks>
/// Instructions and supporting resources are fetched from the MCP server when requested.
/// Fetched instructions must have the same frontmatter name and description as the listing.
/// Instructions and supporting resources must match their listed SHA-256 digest and byte size.
/// Each resource read must return exactly one text or binary content block.
/// Only supporting resources listed by the server are available.
/// </remarks>
internal sealed class AgentMcpListedSkill : AgentSkill
{
    internal const long DefaultMaxResourceSizeBytes = 1024 * 1024;

    private const int MaxResourceNameDecodingDepth = 32;

    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly string _skillUri;
    private readonly string _skillRootUri;
    private readonly IReadOnlyList<McpListedSkillResourceEntry> _resources;
    private readonly long _maxResourceSizeBytes;
    private string? _content;

    /// <summary>
    /// Initializes a skill discovered through <c>skills/list</c>.
    /// </summary>
    /// <param name="frontmatter">The skill's name and description.</param>
    /// <param name="uri">The resource URI of the skill's <c>SKILL.md</c>.</param>
    /// <param name="resources">All resources listed for the skill, including <c>SKILL.md</c>.</param>
    /// <param name="client">The MCP client used to fetch instructions and resources.</param>
    /// <param name="logger">Optional logger for frontmatter parsing diagnostics.</param>
    /// <param name="maxResourceSizeBytes">The maximum allowed resource size in bytes.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="maxResourceSizeBytes"/> is not positive.</exception>
    public AgentMcpListedSkill(AgentSkillFrontmatter frontmatter, string uri, IReadOnlyList<McpListedSkillResourceEntry> resources, McpClient client, ILogger? logger = null, long maxResourceSizeBytes = DefaultMaxResourceSizeBytes)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._skillUri = Throw.IfNullOrWhitespace(uri);
        this._skillRootUri = this._skillUri[..^"SKILL.md".Length];
        this._resources = Throw.IfNull(resources);
        this._client = Throw.IfNull(client);
        this._logger = logger ?? NullLogger.Instance;
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxResourceSizeBytes);
        this._maxResourceSizeBytes = maxResourceSizeBytes;
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Fetches the skill's <c>SKILL.md</c> resource, which contains the skill's instructions, on the first call.
    /// Verifies its digest, byte size, and frontmatter name and description against the listing,
    /// and reuses verified content on later calls.
    /// </remarks>
    /// <exception cref="InvalidOperationException">The skill's <c>SKILL.md</c> resource is not listed,
    /// the response contains multiple content blocks, the fetched content is empty or has invalid frontmatter
    /// or base64, or its digest, byte size, name, or description differs from the listing,
    /// or the resource exceeds the configured size limit.</exception>
    public override async ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
    {
        if (this._content is not null)
        {
            return this._content;
        }

        McpListedSkillResourceEntry? skillMdResource = this._resources.FirstOrDefault(resource => string.Equals(resource.Uri, this._skillUri, StringComparison.Ordinal));
        if (skillMdResource is null)
        {
            throw new InvalidOperationException($"The resource list must include the skill's SKILL.md resource '{this._skillUri}'.");
        }

        ResourceContents content = await this.ReadResourceContentAsync(this._skillUri, cancellationToken).ConfigureAwait(false);

        if (content is not TextResourceContents textContent)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this._skillUri}'.");
        }

        this.VerifyResourceIntegrity(skillMdResource, textContent);

        string text = textContent.Text;

        if (!AgentSkillFrontmatterParser.TryParse(text, this._skillUri, this._logger, out AgentSkillFrontmatter? frontmatter))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this._skillUri}' contains invalid frontmatter.");
        }

        if (!string.Equals(frontmatter.Name, this.Frontmatter.Name, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this._skillUri}' has a frontmatter name that differs from the skills/list entry.");
        }

        if (!string.Equals(frontmatter.Description, this.Frontmatter.Description, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"SKILL.md resource '{this._skillUri}' has a frontmatter description that differs from the skills/list entry.");
        }

        return this._content = text;
    }

    /// <inheritdoc/>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="name"/> is empty or whitespace-only.</exception>
    /// <remarks>
    /// Fetches a supporting resource listed by the server. Returns <see langword="null"/> if the name
    /// is unsafe or the resource is not listed. Errors while fetching the resource are propagated.
    /// Fetched content must match its listed digest and byte size.
    /// </remarks>
    /// <exception cref="InvalidOperationException">The fetched resource has no content or multiple content blocks,
    /// contains invalid base64, exceeds the configured size limit, or does not match its listed digest or byte size.</exception>
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
        if (string.Equals(uri, this._skillUri, StringComparison.Ordinal))
        {
            return null;
        }

        // Supporting reads must stay within the held manifest.
        McpListedSkillResourceEntry? resource = this._resources.FirstOrDefault(resource => string.Equals(resource.Uri, uri, StringComparison.Ordinal));
        if (resource is null)
        {
            return null;
        }

        ResourceContents content = await this.ReadResourceContentAsync(uri, cancellationToken).ConfigureAwait(false);

        this.VerifyResourceIntegrity(resource, content);

        return new AgentMcpListedSkillResource(name, content);
    }

    private async Task<ResourceContents> ReadResourceContentAsync(string uri, CancellationToken cancellationToken)
    {
#pragma warning disable CA2234 // Preserve the exact resource URI advertised by the server.
        ReadResourceResult result = await this._client.ReadResourceAsync(uri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234

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

        return content is BlobResourceContents binary ? this.DecodeBinaryContent(binary, uri) : content;
    }

    private void VerifyResourceIntegrity(McpListedSkillResourceEntry resource, ResourceContents content)
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
                // when ReadResourceContentAsync loaded the binary content.
                byteSize = blob.DecodedData.Length;

                break;
            }

            default:
                throw new InvalidOperationException($"The MCP server returned unsupported content for resource '{resource.Uri}'.");
        }

        // Reject a size mismatch before encoding text or hashing decoded binary content.
        if (byteSize != resource.Size)
        {
            throw new InvalidOperationException($"Resource '{resource.Uri}' has a byte size that differs from the skills/list entry.");
        }

        ReadOnlyMemory<byte> bytes = content switch
        {
            TextResourceContents text => Encoding.UTF8.GetBytes(text.Text),
            BlobResourceContents binary => binary.DecodedData,
            _ => throw new InvalidOperationException("Unsupported listed skill content."),
        };

        string digest = Convert.ToHexString(SHA256.HashData(bytes.Span));

        if (!digest.AsSpan().Equals(resource.Digest.AsSpan("sha256:".Length), StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"Resource '{resource.Uri}' has a SHA-256 digest that differs from the skills/list entry.");
        }
    }

    /// <summary>
    /// Validates Base64 and the decoded size limit, then decodes into an exact-size buffer
    /// without allocating based on Base64 formatting whitespace.
    /// </summary>
    /// <param name="content">The Base64-encoded resource content.</param>
    /// <param name="uri">The requested resource URI used in validation errors.</param>
    /// <returns>Content backed by the decoded bytes, preserving the resource URI, MIME type, and metadata.</returns>
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

    private static string? FullyUnescape(string value)
    {
        // Bound decoding work while still checking that the final pass has stabilized.
        for (int depth = 0; depth <= MaxResourceNameDecodingDepth; depth++)
        {
            string decoded = Uri.UnescapeDataString(value).Replace('\\', '/');

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
