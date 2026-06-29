// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
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
    private const string SharedCacheKey = "";

    private readonly ConcurrentDictionary<string, Task<IList<AgentSkill>>> _cachedTasks = new(StringComparer.Ordinal);
    private readonly CachingAgentSkillsSourceOptions? _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="CachingAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="innerSource">The inner source whose results will be cached.</param>
    /// <param name="options">Optional cache configuration.</param>
    internal CachingAgentSkillsSource(AgentSkillsSource innerSource, CachingAgentSkillsSourceOptions? options = null)
        : base(innerSource)
    {
        this._options = options;
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
        var cacheKey = this._options?.CacheIsolationKeySelector?.Invoke(context) ?? SharedCacheKey;

        var tcs = new TaskCompletionSource<IList<AgentSkill>>(TaskCreationOptions.RunContinuationsAsynchronously);

        while (!this._cachedTasks.TryAdd(cacheKey, tcs.Task))
        {
            if (this._cachedTasks.TryGetValue(cacheKey, out var existing))
            {
                return await existing.ConfigureAwait(false);
            }
        }

        try
        {
            var result = await this.InnerSource.GetSkillsAsync(context, cancellationToken).ConfigureAwait(false);
            tcs.SetResult(result);
            return result;
        }
        catch (OperationCanceledException)
        {
            this._cachedTasks.TryRemove(cacheKey, out _);
            tcs.TrySetCanceled(cancellationToken);
            throw;
        }
        catch (Exception ex)
        {
            this._cachedTasks.TryRemove(cacheKey, out _);
            tcs.TrySetException(ex);
            throw;
        }
    }
}
