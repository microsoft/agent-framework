// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkill"/> discovered from an MCP server exposing the Agent Skills convention.
/// </summary>
/// <remarks>
/// <para>
/// The skill is constructed from <c>skill://index.json</c> discovery metadata only; <see cref="GetContentAsync"/>
/// fetches the full <c>SKILL.md</c> content from the MCP server on demand via <c>resources/read</c>.
/// </para>
/// <para>
/// Per SEP-2640, resources referenced inside SKILL.md are fetched on demand via the originating MCP
/// server: <see cref="GetResourceAsync"/> resolves a relative resource name against the
/// skill's root URI, issues a <c>resources/read</c> request, and returns an <see cref="AgentMcpSkillResource"/>
/// with pre-fetched content.
/// </para>
/// </remarks>
internal sealed partial class AgentMcpSkill : AgentSkill
{
    private const string SkillMdSuffix = "SKILL.md";
    private const int MaxResourceNameDecodingDepth = 32;

    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly string _skillMdUri;
    private readonly string _skillRootUri;
    private string? _content;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkill"/> class.
    /// </summary>
    /// <param name="frontmatter">The parsed frontmatter metadata for this skill.</param>
    /// <param name="skillMdUri">
    /// The full MCP resource URI of the <c>SKILL.md</c> resource (e.g. <c>skill://unit-converter/SKILL.md</c>).
    /// Used by <see cref="GetContentAsync"/> to fetch the skill content on demand. The skill's root URI
    /// (used to resolve sibling resources) is derived by stripping the trailing <c>SKILL.md</c> segment.
    /// </param>
    /// <param name="client">The MCP client used to fetch resources on demand.</param>
    /// <param name="logger">The logger used to report rejected resource names.</param>
    public AgentMcpSkill(AgentSkillFrontmatter frontmatter, string skillMdUri, McpClient client, ILogger logger)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._skillMdUri = Throw.IfNullOrWhitespace(skillMdUri);
        this._skillRootUri = ComputeSkillRootUri(skillMdUri);
        this._client = Throw.IfNull(client);
        this._logger = Throw.IfNull(logger);
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Fetches the <c>SKILL.md</c> content from the MCP server via <c>resources/read</c> on the first call
    /// and caches the result.
    /// </remarks>
    public override async ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
    {
        if (this._content is not null)
        {
            return this._content;
        }

#pragma warning disable CA2234 // Pass system uri objects instead of strings
        ReadResourceResult result = await this._client.ReadResourceAsync(this._skillMdUri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings

        string text = string.Join("\n", result.Contents.OfType<TextResourceContents>().Select(c => c.Text));

        if (text.Length == 0)
        {
            throw new InvalidOperationException($"The MCP server returned no text content for SKILL.md resource '{this._skillMdUri}'.");
        }

        return this._content = text;
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Resolves <paramref name="name"/> as a relative path against the skill's root URI, issues a
    /// <c>resources/read</c> request to the MCP server, and returns an <see cref="AgentMcpSkillResource"/>
    /// with the pre-fetched content. Absolute paths, parent traversal (including percent-encoded forms),
    /// embedded URI schemes, and control characters are rejected before sending a request.
    /// Resource names requiring more than 32 percent-decoding passes are also rejected.
    /// Returns <see langword="null"/> when the name is empty or unsafe, the server
    /// returns no content, or the resource does not exist on the server.
    /// </remarks>
    public override async ValueTask<AgentSkillResource?> GetResourceAsync(string name, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            return null;
        }

        // Treat backslashes as separators, e.g. "..\x" is checked and requested as "../x".
        string normalized = name.Replace('\\', '/');
        if (!IsResourceNameSafe(normalized))
        {
            LogUnsafeResourceName(this._logger);
            return null;
        }

        string uri = this._skillRootUri + normalized;

        ReadResourceResult result;
        try
        {
#pragma warning disable CA2234 // Pass system uri objects instead of strings
            result = await this._client.ReadResourceAsync(uri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return null;
        }

        return new AgentMcpSkillResource(name: name, result: result);
    }

    private static bool IsResourceNameSafe(string normalized)
    {
        // Split at the first literal "?"/"#" before decoding, so "a%3f/%2e%2e/x" stays one path while
        // "a/b.md?q=/../x" leaves "/../x" in the query; then decode each part once.
        string[] parts = normalized.Split(['?', '#'], 2);
        string? path = FullyUnescape(parts[0]);
        string? suffix = FullyUnescape(parts.Length > 1 ? parts[1] : string.Empty);

        // Excessive encoding depth, e.g. a name requiring more than 32 decoding passes.
        return path is not null && suffix is not null
            // Absolute path, e.g. "/etc/passwd" or "%2fetc/passwd".
            && !path.StartsWith('/')
            // Embedded URI, e.g. "http://example.com/other" or "%68ttp%3a%2f%2fexample.com".
            && !path.Contains("://", StringComparison.Ordinal)
            // Parent traversal, e.g. "../x", "%2e%2e/x", "%252e%252e/x", "a%3f/../../x", or ".. " (URI parsers can trim trailing spaces).
            && !path.Split(['/', '?', '#']).Any(segment => segment.TrimEnd(' ') == "..")
            // Control characters anywhere, e.g. "a/\0/b.md", ".\t./x", or ".%09./x".
            && !(path + suffix).Any(char.IsControl);
    }

    /// <summary>
    /// Percent-decodes <paramref name="value"/> until stable, normalizing backslashes to forward slashes.
    /// Decoding never removes a literal <c>.</c>, <c>/</c>, <c>:</c>, or control character, so checking
    /// the final form also covers every nested encoding layer (e.g. <c>%252e</c>).
    /// </summary>
    /// <returns>The decoded value, or <see langword="null"/> if the decoding depth exceeds the limit.</returns>
    private static string? FullyUnescape(string value)
    {
        // The final pass only checks that decoding has stabilized.
        for (int depth = 0; depth <= MaxResourceNameDecodingDepth; depth++)
        {
            string decoded = Uri.UnescapeDataString(value).Replace('\\', '/');
            if (decoded == value)
            {
                return value;
            }

            value = decoded;
        }

        return null;
    }

    [LoggerMessage(LogLevel.Debug, "Rejecting MCP skill resource name with unsafe path components.")]
    private static partial void LogUnsafeResourceName(ILogger logger);

    /// <summary>
    /// Strips the trailing <c>SKILL.md</c> from the URI to produce the skill's root directory URI.
    /// If the URI doesn't end with <c>SKILL.md</c>, ensures it ends with a trailing slash.
    /// </summary>
    private static string ComputeSkillRootUri(string skillMdUri)
    {
        if (skillMdUri.EndsWith(SkillMdSuffix, StringComparison.Ordinal))
        {
            return skillMdUri.Substring(0, skillMdUri.Length - SkillMdSuffix.Length);
        }

        if (skillMdUri.EndsWith("/", StringComparison.Ordinal))
        {
            return skillMdUri;
        }

        return skillMdUri + "/";
    }
}
