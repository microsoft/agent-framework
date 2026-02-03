// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides an in-memory implementation of <see cref="AgentSessionStore"/> for development and testing scenarios.
/// </summary>
/// <remarks>
/// <para>
/// This implementation stores threads in memory using a concurrent dictionary and is suitable for:
/// <list type="bullet">
/// <item><description>Single-instance development scenarios</description></item>
/// <item><description>Testing and prototyping</description></item>
/// <item><description>Scenarios where session persistence across restarts is not required</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Warning:</strong> All stored threads will be lost when the application restarts.
/// For production use with multiple instances or persistence across restarts, use a durable storage implementation
/// such as Redis, SQL Server, or Azure Cosmos DB.
/// </para>
/// </remarks>
public sealed class InMemoryAgentSessionStore : AgentSessionStore
{
    private readonly ConcurrentDictionary<string, JsonElement> _threads = new();

    /// <inheritdoc/>
    public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agent.Id);
        this._threads[key] = session.Serialize();
        return default;
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agent.Id);
        JsonElement? sessionContent = this._threads.TryGetValue(key, out var existingSession) ? existingSession : null;

        return sessionContent switch
        {
            null => await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false),
            _ => await agent.DeserializeSessionAsync(sessionContent.Value, cancellationToken: cancellationToken).ConfigureAwait(false),
        };
    }

    private static string GetKey(string conversationId, string agentId) => $"{agentId}:{conversationId}";
}
