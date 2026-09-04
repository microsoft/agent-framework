// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// This store implementation does not have any store under the hood and therefore does not store sessions.
/// <see cref="GetSessionAsync(AIAgent, AgentSessionStoreKey, CancellationToken)"/> always returns <see langword="null"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class NoopAgentSessionStore : AgentSessionStore
{
    /// <inheritdoc/>
    public override ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        return default;
    }

    /// <inheritdoc/>
    public override ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        return new((AgentSession?)null);
    }
}
