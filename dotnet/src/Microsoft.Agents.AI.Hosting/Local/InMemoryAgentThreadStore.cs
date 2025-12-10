// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides an in-memory implementation of <see cref="AgentThreadStore"/> for development and testing scenarios.
/// </summary>
/// <remarks>
/// <para>
/// This implementation stores threads in memory using a concurrent dictionary and is suitable for:
/// <list type="bullet">
/// <item><description>Single-instance development scenarios</description></item>
/// <item><description>Testing and prototyping</description></item>
/// <item><description>Scenarios where thread persistence across restarts is not required</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Warning:</strong> All stored threads will be lost when the application restarts.
/// For production use with multiple instances or persistence across restarts, use a durable storage implementation
/// such as Redis, SQL Server, or Azure Cosmos DB.
/// </para>
/// </remarks>
public sealed class InMemoryAgentThreadStore : AgentThreadStore
{
    private readonly ConcurrentDictionary<string, JsonElement> _threads = new();

    /// <inheritdoc/>
    public override ValueTask SaveThreadAsync(AIAgent agent, string conversationId, AgentThread thread, CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agent.Id);
        this._threads[key] = thread.Serialize();
        return default;
    }

    /// <inheritdoc/>
    public override ValueTask<AgentThread> GetThreadAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agent.Id);
        JsonElement? threadContent = this._threads.TryGetValue(key, out var existingThread) ? existingThread : null;

        return threadContent switch
        {
            null => new ValueTask<AgentThread>(agent.GetNewThread()),
            _ => new ValueTask<AgentThread>(agent.DeserializeThread(threadContent.Value)),
        };
    }

    private static string GetKey(string conversationId, string agentId) => $"{agentId}:{conversationId}";
}
