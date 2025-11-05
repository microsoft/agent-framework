// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.Entities;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a handle for a running agent request that can be used to retrieve the response.
/// </summary>
internal sealed class AgentRunHandle
{
    private readonly DurableTaskClient _client;

    internal AgentRunHandle(DurableTaskClient client, AgentSessionId sessionId, string correlationId)
    {
        this._client = client;
        this.SessionId = sessionId;
        this.CorrelationId = correlationId;
    }

    /// <summary>
    /// Gets the correlation ID for this request.
    /// </summary>
    public string CorrelationId { get; }

    /// <summary>
    /// Gets the session ID for this request.
    /// </summary>
    public AgentSessionId SessionId { get; }

    /// <summary>
    /// Reads the agent response for this request by polling the entity state until the response is found.
    /// Uses an exponential backoff polling strategy with a maximum interval of 1 second.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The agent response corresponding to this request.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the response is not found after polling.</exception>
    public async Task<AgentRunResponse> ReadAgentResponseAsync(CancellationToken cancellationToken = default)
    {
        TimeSpan pollInterval = TimeSpan.FromMilliseconds(50); // Start with 50ms
        TimeSpan maxPollInterval = TimeSpan.FromSeconds(3); // Maximum 3 seconds

        while (true)
        {
            // Poll the entity state for responses
            EntityMetadata<DurableAgentState>? entityResponse = await this._client.Entities.GetEntityAsync<DurableAgentState>(
                this.SessionId,
                cancellation: cancellationToken);
            DurableAgentState? state = entityResponse?.State;
            if (state?.ConversationHistory != null)
            {
                // Look for an agent response with matching ResponseId
                if (state.TryGetAgentResponse(this.CorrelationId, out AgentRunResponse? response))
                {
                    return response;
                }
            }

            // Wait before polling again with exponential backoff
            await Task.Delay(pollInterval, cancellationToken);

            // Double the poll interval, but cap it at the maximum
            pollInterval = TimeSpan.FromMilliseconds(Math.Min(pollInterval.TotalMilliseconds * 2, maxPollInterval.TotalMilliseconds));
        }
    }
}
