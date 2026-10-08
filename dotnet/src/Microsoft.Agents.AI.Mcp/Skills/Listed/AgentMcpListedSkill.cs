// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill discovered through <c>skills/list</c>.
/// </summary>
/// <remarks>
/// Instructions and supporting resources are fetched from the MCP server when requested.
/// Only supporting resources listed by the server are available.
/// </remarks>
internal sealed class AgentMcpListedSkill : AgentSkill
{
    private const int MaxResourceNameDecodingDepth = 32;

    private readonly McpClient _client;
    private readonly string _skillUri;
    private readonly string _skillRootUri;
    private readonly IReadOnlyList<McpListedSkillResourceEntry> _resources;
    private string? _content;

    /// <summary>
    /// Initializes a skill discovered through <c>skills/list</c>.
    /// </summary>
    /// <param name="frontmatter">The skill's name and description.</param>
    /// <param name="uri">The resource URI of the skill's <c>SKILL.md</c>.</param>
    /// <param name="resources">The skill's supporting resources, excluding <c>SKILL.md</c>.</param>
    /// <param name="client">The MCP client used to fetch instructions and resources.</param>
    public AgentMcpListedSkill(AgentSkillFrontmatter frontmatter, string uri, IReadOnlyList<McpListedSkillResourceEntry> resources, McpClient client)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._skillUri = Throw.IfNullOrWhitespace(uri);
        this._skillRootUri = this._skillUri[..^"SKILL.md".Length];
        this._resources = Throw.IfNull(resources);
        this._client = Throw.IfNull(client);
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Fetches the skill's <c>SKILL.md</c> instructions on the first call and reuses them on later calls.
    /// </remarks>
    public override async ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
    {
        if (this._content is not null)
        {
            return this._content;
        }

#pragma warning disable CA2234 // Pass system uri objects instead of strings
        ReadResourceResult result = await this._client.ReadResourceAsync(this._skillUri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings

        string text = string.Join("\n", result.Contents.OfType<TextResourceContents>().Select(c => c.Text));

        if (text.Length == 0)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this._skillUri}'.");
        }

        return this._content = text;
    }

    /// <inheritdoc/>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="name"/> is empty or whitespace-only.</exception>
    /// <remarks>
    /// Fetches a supporting resource listed by the server. Returns <see langword="null"/> if the name
    /// is unsafe or the resource is not listed. Errors while fetching the resource are propagated.
    /// </remarks>
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

        // Supporting reads must stay within the held manifest.
        if (!this._resources.Any(resource => string.Equals(resource.Uri, uri, StringComparison.Ordinal)))
        {
            return null;
        }

#pragma warning disable CA2234 // Preserve the exact resource URI advertised by the server.
        ReadResourceResult result = await this._client.ReadResourceAsync(uri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234

        return new AgentMcpListedSkillResource(name, result);
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
            && !path.Split(['/', '?', '#']).Any(segment => segment.TrimEnd(' ') == "..")
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
