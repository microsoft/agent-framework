// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source decorator that caches the result of the inner source's <see cref="AgentSkillsSource.GetSkillsAsync"/>
/// call, returning the cached list on subsequent invocations.
/// </summary>
/// <remarks>
/// The cache uses a lock-free, thread-safe pattern so that concurrent callers share
/// a single in-flight fetch and all receive the same cached result.
/// If the initial fetch fails, the cache is not populated and subsequent calls will retry.
/// </remarks>
internal sealed class CachingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private Task<IList<AgentSkill>>? _cachedTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="CachingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source whose results will be cached.</param>
    internal CachingAgentSkillsSource(AgentSkillsSource innerSource)
        : base(innerSource)
    {
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var tcs = new TaskCompletionSource<IList<AgentSkill>>(TaskCreationOptions.RunContinuationsAsynchronously);

        if (Interlocked.CompareExchange(ref this._cachedTask, tcs.Task, null) is { } existing)
        {
            return await existing.ConfigureAwait(false);
        }

        try
        {
            var result = await this.InnerSource.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
            tcs.SetResult(result);
            return result;
        }
        catch (OperationCanceledException)
        {
            Volatile.Write(ref this._cachedTask, null);
            tcs.TrySetCanceled(cancellationToken);
            throw;
        }
        catch (Exception ex)
        {
            Volatile.Write(ref this._cachedTask, null);
            tcs.TrySetException(ex);
            throw;
        }
    }
}
