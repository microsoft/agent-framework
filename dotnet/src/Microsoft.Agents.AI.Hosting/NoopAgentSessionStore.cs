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
    public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        return new ValueTask();
    }

    /// <inheritdoc/>
    public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        return agent.CreateSessionAsync(cancellationToken);
    }
}
