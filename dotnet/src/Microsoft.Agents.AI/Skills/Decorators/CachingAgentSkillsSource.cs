// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// Thread-safe: the first concurrent caller loads from the inner source and all other callers
/// await the same in-flight task. If the load fails, the field is reset so future callers can retry.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class CachingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private Task<IList<AgentSkill>>? _loadTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="CachingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source to cache.</param>
    public CachingAgentSkillsSource(AgentSkillsSource innerSource)
        : base(innerSource)
    {
    }

    /// <inheritdoc/>
    public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return this._loadTask ?? this.LoadAsync(cancellationToken);
    }

    private async Task<IList<AgentSkill>> LoadAsync(CancellationToken cancellationToken)
    {
        var tcs = new TaskCompletionSource<IList<AgentSkill>>(TaskCreationOptions.RunContinuationsAsynchronously);

        if (Interlocked.CompareExchange(ref this._loadTask, tcs.Task, null) is { } existing)
        {
            return await existing.ConfigureAwait(false);
        }

        try
        {
            var result = await this.InnerSource.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
            tcs.SetResult(result);
            return result;
        }
        catch (Exception ex)
        {
            this._loadTask = null;
            tcs.TrySetException(ex);
            throw;
        }
    }
}
