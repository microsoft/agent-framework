// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source decorator that removes duplicate skills by name, keeping only the first occurrence.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed partial class DeduplicatingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private readonly ILogger<DeduplicatingAgentSkillsSource> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="DeduplicatingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source to deduplicate.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public DeduplicatingAgentSkillsSource(AgentSkillsSource innerSource, ILoggerFactory? loggerFactory = null)
        : base(innerSource)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<DeduplicatingAgentSkillsSource>();
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var allSkills = await this.InnerSource.GetSkillsAsync(cancellationToken).ConfigureAwait(false);

        var deduplicated = new List<AgentSkill>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var skill in allSkills)
        {
            if (seen.Add(skill.Frontmatter.Name))
            {
                deduplicated.Add(skill);
            }
            else
            {
                LogDuplicateSkillName(this._logger, skill.Frontmatter.Name);
            }
        }

        return deduplicated;
    }

    [LoggerMessage(LogLevel.Warning, "Duplicate skill name '{SkillName}': subsequent skill skipped in favor of first occurrence")]
    private static partial void LogDuplicateSkillName(ILogger logger, string skillName);
}
