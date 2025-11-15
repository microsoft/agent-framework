// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a client for interacting with a durable agent.
/// </summary>
internal interface IDurableAgentClient
{
    /// <summary>
    /// Runs an agent with the specified request.
    /// </summary>
    /// <param name="sessionId">The ID of the target agent session.</param>
    /// <param name="request">The request containing the message, role, and configuration.</param>
    /// <param name="cancellationToken">The cancellation token for scheduling the request.</param>
    /// <returns>A task that returns a handle used to read the agent response.</returns>
    Task<AgentRunHandle> RunAgentAsync(
        AgentSessionId sessionId,
        RunRequest request,
        CancellationToken cancellationToken = default);
}
