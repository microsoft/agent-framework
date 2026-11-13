// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// A session store that records the agent hosting passes to it, which is the agent the response is served with.
/// It keeps no sessions, so every response starts a new one.
/// </summary>
internal sealed class ServedAgentRecordingStore : AgentSessionStore
{
    public ConcurrentQueue<AIAgent> Agents { get; } = new();

    public override ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        this.Agents.Enqueue(agent);
        return new((AgentSession?)null);
    }

    public override ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        this.Agents.Enqueue(agent);
        return default;
    }

    public override ValueTask DeleteSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default) =>
        default;
}
