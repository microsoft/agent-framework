// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// This store implementation does not have any store under the hood and operates with empty threads.
/// It the "noop" store, and could be used if you are keeping the thread contents on the client side for example.
/// </summary>
public sealed class NoContextAgentThreadStore : IAgentThreadStore
{
    /// <inheritdoc/>
    public ValueTask<JsonElement?> GetOrCreateThreadAsync(string conversationId, string agentId, CancellationToken cancellationToken = default)
    {
        // this is OK, Agents should be prepared to handle null threads.
        return new ValueTask<JsonElement?>(result: null!);
    }

    /// <inheritdoc/>
    public ValueTask SaveThreadAsync(string conversationId, string agentId, AgentThread thread, CancellationToken cancellationToken = default)
    {
        return new();
    }
}
