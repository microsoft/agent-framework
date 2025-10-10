// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentWebChat.Web;

/// <summary>
/// Interface for clients that can interact with agents and provide streaming responses.
/// </summary>
internal abstract class AgentClientBase
{
    /// <summary>
    /// Runs an agent with the specified messages and returns a streaming response.
    /// </summary>
    /// <param name="agentName">The name of the agent to run.</param>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="threadId">Optional thread identifier for conversation continuity.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An asynchronous enumerable of agent response updates.</returns>
    public abstract IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets the agent card for the specified agent (A2A protocol only).
    /// </summary>
    /// <param name="agentName">The name of the agent.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The agent card if supported, null otherwise.</returns>
    public virtual Task<AgentCard?> GetAgentCardAsync(string agentName, CancellationToken cancellationToken = default)
        => Task.FromResult<AgentCard?>(null);
}

/// <summary>
/// Helper class to create a thread-like wrapper for agent clients.
/// </summary>
public class AgentClientThread
{
    public string ThreadId { get; }

    public AgentClientThread(string? threadId = null)
    {
        this.ThreadId = threadId ?? Guid.NewGuid().ToString("N");
    }
}
