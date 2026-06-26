// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides context about the current invocation to <see cref="AgentSkillsSource.GetSkillsAsync"/>.
/// </summary>
/// <remarks>
/// This context is created internally by <see cref="AgentSkillsProvider"/> and passed through the
/// source pipeline, allowing skill sources to make context-aware decisions such as filtering skills
/// per agent.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillsSourceContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsSourceContext"/> class.
    /// </summary>
    /// <param name="agent">The agent that is invoking the skill source.</param>
    /// <exception cref="System.ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public AgentSkillsSourceContext(AIAgent agent)
    {
        this.Agent = Throw.IfNull(agent);
    }

    /// <summary>
    /// Gets the agent that is invoking the skill source.
    /// </summary>
    public AIAgent Agent { get; }
}
