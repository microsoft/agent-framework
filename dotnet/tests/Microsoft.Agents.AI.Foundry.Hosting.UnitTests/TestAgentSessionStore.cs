// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

internal sealed class TestAgentSessionStore : AgentSessionStore
{
    private readonly ConcurrentDictionary<(string AgentIdentity, AgentSessionStoreKey Key), JsonElement> _sessions = new();
    private int _saveCount;

    /// <summary>Gets how many times a session was saved.</summary>
    internal int SaveCount => Volatile.Read(ref this._saveCount);

    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref this._saveCount);
        this._sessions[GetKey(agent, key)] =
            await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
        => this._sessions.TryGetValue(GetKey(agent, key), out JsonElement serializedSession)
            ? await agent.DeserializeSessionAsync(serializedSession, cancellationToken: cancellationToken).ConfigureAwait(false)
            : null;

    public override ValueTask DeleteSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        this._sessions.TryRemove(GetKey(agent, key), out _);
        return default;
    }

    private static (string AgentIdentity, AgentSessionStoreKey Key) GetKey(
        AIAgent agent,
        AgentSessionStoreKey key)
        => (FoundryHostingAgent.GetSessionStorageIdentity(agent, allowInstanceId: true), key);
}
