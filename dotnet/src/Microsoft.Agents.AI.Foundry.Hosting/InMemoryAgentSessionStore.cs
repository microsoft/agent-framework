// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides an in-memory implementation of <see cref="AgentSessionStore"/> for development and testing scenarios.
/// </summary>
/// <remarks>
/// <para>
/// This implementation stores sessions in memory using a concurrent dictionary and is suitable for:
/// <list type="bullet">
/// <item><description>Single-instance development scenarios</description></item>
/// <item><description>Testing and prototyping</description></item>
/// <item><description>Scenarios where session persistence across restarts is not required</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Warning:</strong> All stored sessions will be lost when the application restarts.
/// For production use with multiple instances or persistence across restarts, use a durable storage implementation
/// such as Redis, SQL Server, or Azure Cosmos DB.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class InMemoryAgentSessionStore : AgentSessionStore
{
    private readonly ConcurrentDictionary<string, JsonElement> _sessions = new();

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, string? userId, CancellationToken cancellationToken = default)
    {
        var key = GetKey(agent, conversationId, userId);
        this._sessions[key] = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, string? userId, CancellationToken cancellationToken = default)
    {
        var key = GetKey(agent, conversationId, userId);
        JsonElement? sessionContent = this._sessions.TryGetValue(key, out var existingSession) ? existingSession : null;

        return sessionContent switch
        {
            null => await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false),
            _ => await agent.DeserializeSessionAsync(sessionContent.Value, cancellationToken: cancellationToken).ConfigureAwait(false),
        };
    }

    // Keyed with the same a-/u-/c- prefix scheme as FileSystemAgentSessionStore so the in-memory store
    // partitions per agent and per user identically. Like FileSystemAgentSessionStore, the agent segment
    // uses agent.Name (a stable identity) and is omitted when no name is set; agent.Id is intentionally
    // NOT used because it is regenerated on every startup for in-memory-defined agents, which would break
    // session continuity for a transient or recreated agent. The user segment is omitted when no user id
    // is supplied.
    private static string GetKey(AIAgent agent, string conversationId, string? userId)
    {
        string key = string.Empty;
        if (!string.IsNullOrEmpty(agent.Name))
        {
            key += $"a-{agent.Name}:";
        }

        if (!string.IsNullOrWhiteSpace(userId))
        {
            key += $"u-{userId}:";
        }

        return key + $"c-{conversationId}";
    }
}
