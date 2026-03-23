// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source decorator that caches the result of the first <see cref="GetSkillsAsync"/> call.
/// </summary>
/// <remarks>
/// Thread-safe: concurrent first callers may redundantly load from the inner source, but the result
/// is idempotent and subsequent calls always return the cached value.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CachingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private IList<AgentSkill>? _cachedSkills;

    /// <summary>
    /// Initializes a new instance of the <see cref="CachingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source to cache.</param>
    public CachingAgentSkillsSource(AgentSkillsSource innerSource)
        : base(innerSource)
    {
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return this._cachedSkills ??= await this.InnerSource.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
    }
}
