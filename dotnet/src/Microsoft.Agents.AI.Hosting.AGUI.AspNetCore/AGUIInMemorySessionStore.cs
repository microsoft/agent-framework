// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal sealed class AGUIInMemorySessionStore : IDisposable
{
    private readonly MemoryCache _cache;
    private readonly MemoryCacheEntryOptions _entryOptions;

    public AGUIInMemorySessionStore()
        : this(options: null)
    {
    }

    internal AGUIInMemorySessionStore(AGUIInMemorySessionStoreOptions? options)
    {
        AGUIInMemorySessionStoreOptions resolvedOptions = options ?? new();
        this._cache = new MemoryCache(resolvedOptions.ToMemoryCacheOptions());
        this._entryOptions = resolvedOptions.ToMemoryCacheEntryOptions();
    }

    public ValueTask<AgentSession> GetOrCreateSessionAsync(AIAgent agent, string threadId, CancellationToken cancellationToken = default)
    {
        string key = GetKey(agent, threadId);
        if (this._cache.TryGetValue(key, out AgentSession? session) && session is not null)
        {
            return new(session);
        }

        return this.CreateAndStoreSessionAsync(agent, key, cancellationToken);
    }

    public ValueTask SaveSessionAsync(AIAgent agent, string threadId, AgentSession session, CancellationToken cancellationToken = default)
    {
        this._cache.Set(GetKey(agent, threadId), session, this._entryOptions);
        return ValueTask.CompletedTask;
    }

    private async ValueTask<AgentSession> CreateAndStoreSessionAsync(AIAgent agent, string key, CancellationToken cancellationToken)
    {
        AgentSession session = await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        return this._cache.GetOrCreate(key, entry =>
        {
            entry.SetOptions(this._entryOptions);
            return session;
        })!;
    }

    public void Dispose()
    {
        this._cache.Dispose();
    }

    private static string GetKey(AIAgent agent, string threadId) => $"{agent.Id}:{threadId}";
}

internal sealed class AGUIInMemorySessionStoreOptions
{
    public long? SizeLimit { get; set; } = 1000;

    public TimeSpan? AbsoluteExpirationRelativeToNow { get; set; }

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