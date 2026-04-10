// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides an in-memory <see cref="AgentSessionStore"/> implementation for AG-UI hosted agents.
/// </summary>
/// <remarks>
/// This store is intended for single-instance development and testing scenarios. Applications that need
/// durable or distributed session persistence can replace the registered <see cref="AgentSessionStore"/>
/// service with a custom implementation.
/// </remarks>
public sealed class AGUIInMemorySessionStore : AgentSessionStore, IDisposable
{
    private readonly MemoryCache _cache;
    private readonly MemoryCacheEntryOptions _entryOptions;
    private readonly ConcurrentDictionary<SessionCacheKey, TaskCompletionSource<AgentSession>> _sessionInitializationTasks = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIInMemorySessionStore"/> class with default options.
    /// </summary>
    public AGUIInMemorySessionStore()
        : this(options: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIInMemorySessionStore"/> class.
    /// </summary>
    /// <param name="options">The cache options to apply. If <see langword="null"/>, default options are used.</param>
    public AGUIInMemorySessionStore(AGUIInMemorySessionStoreOptions? options)
    {
        AGUIInMemorySessionStoreOptions resolvedOptions = options ?? new();
        this._cache = new MemoryCache(resolvedOptions.ToMemoryCacheOptions());
        this._entryOptions = resolvedOptions.ToMemoryCacheEntryOptions();
    }

    /// <inheritdoc/>
    public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
        => this.GetOrCreateSessionAsync(agent, conversationId, cancellationToken);

    /// <summary>
    /// Gets the session for the specified conversation or creates a new one when none exists.
    /// </summary>
    /// <param name="agent">The agent that owns the session.</param>
    /// <param name="threadId">The conversation or thread identifier.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The existing or newly created session.</returns>
    public ValueTask<AgentSession> GetOrCreateSessionAsync(AIAgent agent, string threadId, CancellationToken cancellationToken = default)
    {
        SessionCacheKey key = GetKey(agent, threadId);
        if (this._cache.TryGetValue(key, out AgentSession? session) && session is not null)
        {
            return new(session);
        }

        return this.GetOrCreateSessionCoreAsync(agent, key, cancellationToken);
    }

    /// <inheritdoc/>
    public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        this._cache.Set(GetKey(agent, conversationId), session, this._entryOptions);
        return ValueTask.CompletedTask;
    }

    private async ValueTask<AgentSession> GetOrCreateSessionCoreAsync(AIAgent agent, SessionCacheKey key, CancellationToken cancellationToken)
    {
        TaskCompletionSource<AgentSession> initializationTask = new(TaskCreationOptions.RunContinuationsAsynchronously);
        TaskCompletionSource<AgentSession> sharedInitializationTask = this._sessionInitializationTasks.GetOrAdd(key, initializationTask);

        if (ReferenceEquals(sharedInitializationTask, initializationTask))
        {
            if (this._cache.TryGetValue(key, out AgentSession? existingSession) && existingSession is not null)
            {
                initializationTask.TrySetResult(existingSession);
                this._sessionInitializationTasks.TryRemove(new KeyValuePair<SessionCacheKey, TaskCompletionSource<AgentSession>>(key, initializationTask));
            }
            else
            {
                _ = this.InitializeSessionAsync(agent, key, initializationTask);
            }
        }

        return await sharedInitializationTask.Task.WaitAsync(cancellationToken).ConfigureAwait(false);
    }

    private async Task<AgentSession> CreateAndStoreSessionAsync(AIAgent agent, SessionCacheKey key)
    {
        AgentSession session = await agent.CreateSessionAsync(CancellationToken.None).ConfigureAwait(false);
        return this._cache.GetOrCreate(key, entry =>
        {
            entry.SetOptions(this._entryOptions);
            return session;
        })!;
    }

    private async Task InitializeSessionAsync(AIAgent agent, SessionCacheKey key, TaskCompletionSource<AgentSession> initializationTask)
    {
        try
        {
            AgentSession session = await this.CreateAndStoreSessionAsync(agent, key).ConfigureAwait(false);
            initializationTask.TrySetResult(session);
        }
        catch (Exception ex)
        {
            initializationTask.TrySetException(ex);
        }
        finally
        {
            this._sessionInitializationTasks.TryRemove(new KeyValuePair<SessionCacheKey, TaskCompletionSource<AgentSession>>(key, initializationTask));
        }
    }

    /// <summary>
    /// Releases the underlying memory cache.
    /// </summary>
    public void Dispose()
    {
        this._cache.Dispose();
    }

    private static SessionCacheKey GetKey(AIAgent agent, string threadId) => new(agent.Id, threadId);

    private sealed record SessionCacheKey(string AgentId, string ThreadId);
}

/// <summary>
/// Configures the default <see cref="AGUIInMemorySessionStore"/> registration used by <c>AddAGUI</c>.
/// </summary>
public sealed class AGUIInMemorySessionStoreOptions
{
    /// <summary>
    /// Gets or sets the maximum number of sessions to retain in memory.
    /// </summary>
    public long? SizeLimit { get; set; } = 1000;

    /// <summary>
    /// Gets or sets the absolute expiration applied to cached sessions.
    /// </summary>
    public TimeSpan? AbsoluteExpirationRelativeToNow { get; set; }

    /// <summary>
    /// Gets or sets the sliding expiration applied to cached sessions.
    /// </summary>
    public TimeSpan? SlidingExpiration { get; set; } = TimeSpan.FromHours(1);

    internal MemoryCacheOptions ToMemoryCacheOptions() => new()
    {
        SizeLimit = this.SizeLimit
    };

    internal MemoryCacheEntryOptions ToMemoryCacheEntryOptions() => new()
    {
        AbsoluteExpirationRelativeToNow = this.AbsoluteExpirationRelativeToNow,
        SlidingExpiration = this.SlidingExpiration,
        Size = 1
    };
}