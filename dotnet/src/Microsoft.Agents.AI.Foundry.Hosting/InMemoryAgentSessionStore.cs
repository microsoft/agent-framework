// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides in-memory session storage using Foundry hosting agent identities.
/// </summary>
/// <remarks>
/// Uses the resolved hosting identity when available, otherwise the agent name, or the process-local
/// agent ID for unnamed agents. Storage and snapshot behavior are provided by
/// <see cref="AI.InMemoryAgentSessionStore"/>. Sessions are lost when the process exits.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class InMemoryAgentSessionStore : AI.InMemoryAgentSessionStore
{
    /// <inheritdoc/>
    protected override string GetAgentIdentity(AIAgent agent)
        => FoundryHostingAgent.GetSessionStorageIdentity(agent, allowInstanceId: true);
}
