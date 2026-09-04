// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

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
/// <para>
/// <strong>Multi-user warning.</strong> This store partitions sessions by the <c>userId</c> supplied
/// to <see cref="AgentSessionStore.GetSessionAsync"/> and <see cref="AgentSessionStore.SaveSessionAsync"/>.
/// Multi-user hosts must supply a trusted user identifier, either directly or by wrapping this store in
/// <see cref="IsolationKeyScopedAgentSessionStore"/> (typically by calling
/// <c>UseClaimsBasedAgentIsolation(...)</c> from
/// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c> or by registering a custom
/// <see cref="AgentIsolationKeyProvider"/>). Passing <see langword="null"/> uses a shared, unscoped
/// partition that is only appropriate for single-user applications and local development.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class InMemoryAgentSessionStore : AgentSessionStore
{
    private readonly ConcurrentDictionary<(string AgentId, AgentSessionStoreKey Key), JsonElement> _sessions = new();

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(agent);
        _ = Throw.IfNull(key);
        _ = Throw.IfNull(session);

        var storageKey = (agent.Id, key);
        this._sessions[storageKey] = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(agent);
        _ = Throw.IfNull(key);

        return this._sessions.TryGetValue((agent.Id, key), out JsonElement existingSession)
            ? await agent.DeserializeSessionAsync(existingSession, cancellationToken: cancellationToken).ConfigureAwait(false)
            : null;
    }
}
