// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
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
internal sealed class AgentMcpSkill : AgentSkill
{
    private const string SkillMdSuffix = "SKILL.md";

    private readonly McpClient _client;
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
    public AgentMcpSkill(AgentSkillFrontmatter frontmatter, string skillMdUri, McpClient client)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._skillMdUri = Throw.IfNullOrWhitespace(skillMdUri);
        this._skillRootUri = ComputeSkillRootUri(skillMdUri);
        this._client = Throw.IfNull(client);
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
    /// with the pre-fetched content. Returns <see langword="null"/> when the name is empty, the server
    /// returns no content, or the resource does not exist on the server.
    /// </remarks>
    public override async ValueTask<AgentSkillResource?> GetResourceAsync(string name, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            return null;
        }

        string uri = this._skillRootUri + name;

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
