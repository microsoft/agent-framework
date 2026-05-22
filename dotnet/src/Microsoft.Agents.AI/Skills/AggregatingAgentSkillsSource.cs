// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source that aggregates multiple child sources, preserving their registration order.
/// </summary>
/// <remarks>
/// Skills from each child source are returned in the order the sources were registered,
/// with each source's skills appended sequentially. No deduplication or filtering is applied.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AggregatingAgentSkillsSource : AgentSkillsSource
{
    private readonly IEnumerable<AgentSkillsSource> _sources;

    /// <summary>
    /// Initializes a new instance of the <see cref="AggregatingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="sources">The child sources to aggregate.</param>
    public AggregatingAgentSkillsSource(IEnumerable<AgentSkillsSource> sources)
    {
        this._sources = Throw.IfNull(sources);
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var allSkills = new List<AgentSkill>();
        foreach (var source in this._sources)
        {
            var skills = await source.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
            allSkills.AddRange(skills);
        }

        return allSkills;
    }
}
