// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Provides an interface for retrieving agent cards in an A2A (Agent-to-Agent) communication context.
/// </summary>
public interface IA2AAgentCardProvider
{
    /// <summary>
    /// Retrieves the agent card for a given agent URL.
    /// </summary>
    /// <param name="agentPath"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken);
}
