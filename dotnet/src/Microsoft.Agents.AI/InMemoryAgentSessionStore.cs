// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

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
/// <para>
/// Sessions are isolated by the agent's <see cref="AIAgent.Id"/> and every partition in
/// <see cref="AgentSessionStoreKey"/>. Hosts must construct partitions from trusted identity data.
/// A key without partitions is appropriate only when no additional user or tenant isolation is needed.
/// </para>
/// <para>
/// Each lookup deserializes an independent session. Concurrent saves to the same key replace the
/// previous snapshot; callers must coordinate concurrent turns if updates must not be lost.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class InMemoryAgentSessionStore : AgentSessionStore
{
    private readonly ConcurrentDictionary<(string AgentIdentity, AgentSessionStoreKey Key), JsonElement> _sessions = new();

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

        var storageKey = (this.GetAgentIdentity(agent), key);
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

        return this._sessions.TryGetValue((this.GetAgentIdentity(agent), key), out JsonElement existingSession)
            ? await agent.DeserializeSessionAsync(existingSession, cancellationToken: cancellationToken).ConfigureAwait(false)
            : null;
    }

    /// <summary>
    /// Gets the identity used to isolate an agent's stored sessions.
    /// </summary>
    /// <param name="agent">The agent that owns the session.</param>
    /// <returns>The agent's storage identity. The default is <see cref="AIAgent.Id"/>.</returns>
    /// <remarks>
    /// Hosting adapters may override this method to supply a stable hosting identity. The same
    /// identity must be returned for save and lookup operations that should share stored sessions.
    /// </remarks>
    protected virtual string GetAgentIdentity(AIAgent agent) => Throw.IfNull(agent).Id;
}
