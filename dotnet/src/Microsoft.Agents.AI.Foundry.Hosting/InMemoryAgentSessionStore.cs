// Copyright (c) Microsoft. All rights reserved.

using System;
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
    private readonly ConcurrentDictionary<(string AgentIdentity, AgentSessionStoreKey Key), JsonElement> _sessions = new();

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(session);

        var storageKey = GetKey(agent, key);
        this._sessions[storageKey] = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(key);

        if (!this._sessions.TryGetValue(GetKey(agent, key), out var existingSession))
        {
            return null;
        }

        return await agent.DeserializeSessionAsync(existingSession, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static (string AgentIdentity, AgentSessionStoreKey Key) GetKey(
        AIAgent agent,
        AgentSessionStoreKey key)
        => (FoundryHostingAgent.GetSessionStorageIdentity(agent, allowInstanceId: true), key);
}
