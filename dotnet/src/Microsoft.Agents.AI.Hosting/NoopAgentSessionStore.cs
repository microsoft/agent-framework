// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// This store implementation does not have any store under the hood and therefore does not store sessions.
/// <see cref="GetSessionAsync(AIAgent, string, CancellationToken)"/> always returns a new session.
/// </summary>
public sealed class NoopAgentSessionStore : AgentSessionStore
{
    /// <inheritdoc/>
    public override ValueTask SaveSessionAsync(AIAgent agent, string sessionStoreId, AgentSession session, CancellationToken cancellationToken = default)
    {
        return default;
    }

    /// <inheritdoc/>
    public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string sessionStoreId, CancellationToken cancellationToken = default)
    {
        return agent.CreateSessionAsync(cancellationToken);
    }

    /// <inheritdoc/>
    public override ValueTask DeleteSessionAsync(AIAgent agent, string sessionStoreId, CancellationToken cancellationToken = default)
    {
        return default;
    }
}
