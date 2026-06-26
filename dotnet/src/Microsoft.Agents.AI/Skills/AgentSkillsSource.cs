// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for skill sources. A skill source provides skills from a specific origin
/// (filesystem, remote server, database, in-memory, etc.).
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSkillsSource
{
    /// <summary>
    /// Gets the skills provided by this source.
    /// </summary>
    /// <param name="context">The context for the current invocation, exposing the invoking <see cref="AIAgent"/>.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A collection of skills from this source.</returns>
    public abstract Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default);
}
