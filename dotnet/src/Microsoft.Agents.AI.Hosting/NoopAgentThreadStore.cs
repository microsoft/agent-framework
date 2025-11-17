// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// This store implementation does not have any store under the hood and operates with empty threads.
/// It is the "noop" store, and could be used if you are keeping the thread contents on the client side for example.
/// </summary>
public sealed class NoopAgentThreadStore : AgentThreadStore
{
    /// <inheritdoc/>
    public override ValueTask SaveThreadAsync(AIAgent agent, string conversationId, AgentThread thread, CancellationToken cancellationToken = default)
    {
        return new ValueTask();
    }

    /// <inheritdoc/>
    public override ValueTask<AgentThread> GetThreadAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        return new ValueTask<AgentThread>(agent.GetNewThread());
    }
}
