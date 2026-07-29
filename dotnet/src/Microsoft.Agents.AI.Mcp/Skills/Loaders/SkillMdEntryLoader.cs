// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI;

/// <summary>
/// Loads <c>skill-md</c> index entries: each entry's <c>SKILL.md</c> and sibling resources are
/// fetched on demand from the MCP server via an <see cref="AgentMcpSkill"/>.
/// </summary>
internal sealed partial class SkillMdEntryLoader : IMcpSkillEntryLoader
{
    private readonly McpClient _client;
    private readonly ILogger _logger;

    public SkillMdEntryLoader(McpClient client, ILoggerFactory loggerFactory)
    {
        this._client = client;
        this._logger = loggerFactory.CreateLogger<SkillMdEntryLoader>();
    }

    /// <inheritdoc/>
    public string EntryType => "skill-md";

    /// <inheritdoc/>
    public Task<IList<AgentSkill>> LoadAsync(IReadOnlyList<McpSkillIndexEntry> entries, AgentSkillsSourceContext context, CancellationToken cancellationToken)
    {
        var skills = new List<AgentSkill>();

        foreach (var entry in entries)
        {
            if (this.TryLoadSkillMdEntry(entry, out AgentSkill? skill))
            {
                skills.Add(skill);
            }
        }

        return Task.FromResult<IList<AgentSkill>>(skills);
    }

    private bool TryLoadSkillMdEntry(McpSkillIndexEntry entry, [NotNullWhen(true)] out AgentSkill? skill)
    {
        skill = null;

        if (string.IsNullOrWhiteSpace(entry.Url))
        {
            LogIndexEntrySkipped(this._logger, entry.Name ?? "(unnamed)", "missing required 'url' field");
            return false;
        }

        AgentSkillFrontmatter frontmatter;
        try
        {
            frontmatter = new AgentSkillFrontmatter(entry.Name!, entry.Description!);
        }
        catch (ArgumentException ex)
        {
            LogIndexEntrySkipped(this._logger, entry.Name ?? "(unnamed)", $"invalid metadata: {ex.Message}");
            return false;
        }

        skill = new AgentMcpSkill(frontmatter, entry.Url!, this._client);

        LogSkillLoaded(this._logger, frontmatter.Name);

        return true;
    }

    [LoggerMessage(LogLevel.Information, "Loaded MCP skill: {SkillName}")]
    private static partial void LogSkillLoaded(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Debug, "Skipping skill index entry '{SkillName}': {Reason}")]
    private static partial void LogIndexEntrySkipped(ILogger logger, string skillName, string reason);
}
