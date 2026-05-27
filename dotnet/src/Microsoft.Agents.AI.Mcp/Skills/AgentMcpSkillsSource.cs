// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
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
/// An <see cref="AgentSkillsSource"/> that discovers Agent Skills served over the Model Context Protocol (MCP).
/// </summary>
/// <remarks>
/// <para>
/// Discovery follows the SEP-2640 recommended approach: the source reads the well-known
/// <c>skill://index.json</c> resource and constructs one <see cref="AgentSkill"/> per
/// <c>skill-md</c> entry directly from the entry's <c>name</c>, <c>description</c>, and <c>url</c> fields.
/// The referenced <c>SKILL.md</c> resource is not read during discovery; hosts fetch its body on
/// demand via <c>resources/read</c> against the URI exposed on the resulting skill.
/// </para>
/// <para>
/// Only index entries of type <c>skill-md</c> are supported at the moment; entries of any other
/// type are skipped.
/// </para>
/// <para>
/// If <c>skill://index.json</c> is absent, unreadable, empty, or fails to parse, this source
/// returns an empty list. Discovered skills serve their referenced resources on demand via
/// <see cref="AgentSkill.GetResourceAsync"/>; they do not enumerate sibling files up front.
/// </para>
/// </remarks>
internal sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    /// <summary>
    /// SEP-2640 canonical discovery document URI.
    /// </summary>
    private const string IndexUri = "skill://index.json";

    private const string SkillMdEntryType = "skill-md";

    private readonly McpClient _client;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that exposes Agent Skills resources.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentMcpSkillsSource(McpClient client, ILoggerFactory? loggerFactory = null)
    {
        this._client = Throw.IfNull(client);
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<AgentMcpSkillsSource>();
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        McpSkillIndex? index = await this.TryReadIndexAsync(cancellationToken).ConfigureAwait(false);

        var skills = new List<AgentSkill>();

        foreach (var entry in index?.Skills ?? [])
        {
            if (this.TryCreateSkill(entry, out AgentMcpSkill? skill, out string skipReason))
            {
                skills.Add(skill);
                LogSkillLoaded(this._logger, skill.Frontmatter.Name);
            }
            else
            {
                LogIndexEntrySkipped(this._logger, entry.Name ?? "(unnamed)", skipReason);
            }
        }

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    private async Task<McpSkillIndex?> TryReadIndexAsync(CancellationToken cancellationToken)
    {
        ReadResourceResult result;

        try
        {
#pragma warning disable CA2234 // Pass system uri objects instead of strings
            result = await this._client.ReadResourceAsync(IndexUri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings
        }
        catch (McpException ex) when (ex is McpProtocolException pex && pex.ErrorCode == McpErrorCode.ResourceNotFound)
        {
            LogIndexAbsent(this._logger, ex.Message);
            return null;
        }
        catch (McpException ex)
        {
            LogIndexReadFailed(this._logger, ex);
            return null;
        }

        string? indexText = result.Contents.OfType<TextResourceContents>().FirstOrDefault()?.Text;
        if (string.IsNullOrWhiteSpace(indexText))
        {
            LogIndexEmpty(this._logger);
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize(indexText, McpJsonContext.Default.McpSkillIndex);
        }
        catch (JsonException ex)
        {
            LogIndexParseFailed(this._logger, ex);
            return null;
        }
    }

    private bool TryCreateSkill(
        McpSkillIndexEntry entry,
        [NotNullWhen(true)] out AgentMcpSkill? skill,
        out string skipReason)
    {
        skill = null;

        if (!string.Equals(entry.Type, SkillMdEntryType, StringComparison.Ordinal))
        {
            skipReason = $"unsupported type '{entry.Type ?? "(none)"}'";
            return false;
        }

        if (string.IsNullOrWhiteSpace(entry.Url))
        {
            skipReason = "missing required 'url' field";
            return false;
        }

        AgentSkillFrontmatter frontmatter;
        try
        {
            frontmatter = new AgentSkillFrontmatter(entry.Name!, entry.Description!);
        }
        catch (ArgumentException ex)
        {
            skipReason = $"invalid metadata: {ex.Message}";
            return false;
        }

        skill = new AgentMcpSkill(frontmatter, entry.Url!, this._client);
        skipReason = string.Empty;
        return true;
    }

    [LoggerMessage(LogLevel.Information, "Loaded MCP skill: {SkillName}")]
    private static partial void LogSkillLoaded(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    [LoggerMessage(LogLevel.Debug, "No skill://index.json resource available on MCP server: {Reason}")]
    private static partial void LogIndexAbsent(ILogger logger, string reason);

    [LoggerMessage(LogLevel.Warning, "Failed to read skill://index.json from MCP server.")]
    private static partial void LogIndexReadFailed(ILogger logger, Exception exception);

    [LoggerMessage(LogLevel.Debug, "skill://index.json on MCP server returned empty/non-text contents")]
    private static partial void LogIndexEmpty(ILogger logger);

    [LoggerMessage(LogLevel.Warning, "Failed to parse skill://index.json JSON document.")]
    private static partial void LogIndexParseFailed(ILogger logger, Exception exception);

    [LoggerMessage(LogLevel.Debug, "Skipping skill index entry '{SkillName}': {Reason}")]
    private static partial void LogIndexEntrySkipped(ILogger logger, string skillName, string reason);
}
