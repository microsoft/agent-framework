// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides contextual information to a skill filter predicate.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillFilterContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillFilterContext"/> class.
    /// </summary>
    /// <param name="skill">The skill being evaluated by the filter.</param>
    /// <param name="skillsSourceContext">Contextual information about the agent and session requesting skills.</param>
    internal AgentSkillFilterContext(AgentSkill skill, AgentSkillsSourceContext skillsSourceContext)
    {
        this.Skill = Throw.IfNull(skill);
        this.SkillsSourceContext = Throw.IfNull(skillsSourceContext);
    }

    /// <summary>
    /// Gets the skill being evaluated by the filter.
    /// </summary>
    public AgentSkill Skill { get; }

    /// <summary>
    /// Gets contextual information about the agent and session requesting skills.
    /// </summary>
    public AgentSkillsSourceContext SkillsSourceContext { get; }
}
