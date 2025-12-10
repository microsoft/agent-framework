// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Handler for processing responses from the agent. This is typically used to send messages to the user.
/// </summary>
public interface IAgentResponseHandler
{
    /// <summary>
    /// Handles a streaming response update from the agent. This is typically used to send messages to the user.
    /// </summary>
    /// <param name="messageStream">
    /// The stream of messages from the agent.
    /// </param>
    /// <param name="cancellationToken">
    /// Signals that the operation should be cancelled.
    /// </param>
    ValueTask OnStreamingResponseUpdateAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> messageStream,
        CancellationToken cancellationToken);

    /// <summary>
    /// Handles a discrete response from the agent. This is typically used to send messages to the user.
    /// </summary>
    /// <param name="message">
    /// The message from the agent.
    /// </param>
    /// <param name="cancellationToken">
    /// Signals that the operation should be cancelled.
    /// </param>
    ValueTask OnAgentResponseAsync(
        AgentRunResponse message,
        CancellationToken cancellationToken);
}
