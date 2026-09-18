// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source decorator that filters skills using a caller-supplied predicate.
/// </summary>
/// <remarks>
/// Skills for which the predicate returns <see langword="true"/> are included in the result;
/// skills for which it returns <see langword="false"/> are excluded and logged at debug level.
/// </remarks>
public sealed partial class FilteringAgentSkillsSource : DelegatingAgentSkillsSource
{
    private readonly Func<AgentSkill, AgentSkillsSourceContext, bool> _predicate;
    private readonly ILogger<FilteringAgentSkillsSource> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="FilteringAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source whose skills will be filtered.</param>
    /// <param name="predicate">
    /// A predicate that determines which skills to include. Skills for which the predicate
    /// returns <see langword="true"/> are kept; others are excluded.
    /// </param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public FilteringAgentSkillsSource(
        AgentSkillsSource innerSource,
        Func<AgentSkill, AgentSkillsSourceContext, bool> predicate,
        ILoggerFactory? loggerFactory = null)
        : base(innerSource)
    {
        this._predicate = Throw.IfNull(predicate);
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<FilteringAgentSkillsSource>();
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
        var allSkills = await this.InnerSource.GetSkillsAsync(context, cancellationToken).ConfigureAwait(false);

        var filtered = new List<AgentSkill>();
        foreach (var skill in allSkills)
        {
            if (this._predicate(skill, context))
            {
                filtered.Add(skill);
            }
            else
            {
                LogSkillFiltered(this._logger, skill.Frontmatter.Name);
            }
        }

        return filtered;
    }

    [LoggerMessage(LogLevel.Debug, "Skill '{SkillName}' excluded by filter predicate")]
    private static partial void LogSkillFiltered(ILogger logger, string skillName);
}
