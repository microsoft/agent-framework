// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source that holds <see cref="AgentSkill"/> instances in memory.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AgentInMemorySkillsSource : AgentSkillsSource
{
    private readonly List<AgentSkill> _skills;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInMemorySkillsSource"/> class.
    /// </summary>
    /// <param name="skills">The skills to include in this source.</param>
    public AgentInMemorySkillsSource(IEnumerable<AgentSkill> skills)
    {
        this._skills = Throw.IfNull(skills).ToList();
    }

    /// <inheritdoc/>
    public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult<IList<AgentSkill>>(this._skills);
    }
}
