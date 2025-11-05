// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a single entry in the durable agent state, which can either be a chat message or agent response.
/// This maintains chronological order of all interactions while preserving strong typing.
/// </summary>
public sealed class AgentStateEntry
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentStateEntry"/> class.
    /// </summary>
    /// <param name="chatMessage">The chat message, if this entry represents a chat message.</param>
    /// <param name="agentResponse">The agent response, if this entry represents an agent response.</param>
    /// <param name="correlationId">The correlation ID associated with the agent response, if any.</param>
    [JsonConstructor]
    public AgentStateEntry(ChatMessage? chatMessage, AgentRunResponse? agentResponse, string? correlationId)
    {
        this.ChatMessage = chatMessage;
        this.AgentResponse = agentResponse;
        this.Type = agentResponse is null ? EntryType.ChatMessage : EntryType.AgentResponse;
        this.CorrelationId = correlationId;
    }

    /// <summary>
    /// Gets the type of this state entry.
    /// </summary>
    public EntryType Type { get; }

    /// <summary>
    /// Gets the correlation ID for this entry.
    /// </summary>
    public string? CorrelationId { get; }

    /// <summary>
    /// Gets the chat message, if this entry is a chat message.
    /// </summary>
    public ChatMessage? ChatMessage { get; }

    /// <summary>
    /// Gets the agent response, if this entry is an agent response.
    /// </summary>
    public AgentRunResponse? AgentResponse { get; }

    /// <summary>
    /// Creates a chat message entry.
    /// </summary>
    /// <param name="message">The chat message.</param>
    /// <returns>A new chat message entry.</returns>
    public static AgentStateEntry CreateChatMessage(ChatMessage message) => new(message, null, null);

    /// <summary>
    /// Creates an agent response entry.
    /// </summary>
    /// <param name="response">The agent response.</param>
    /// <param name="correlationId">The correlation ID for the agent response.</param>
    /// <returns>A new agent response entry.</returns>
    public static AgentStateEntry CreateAgentResponse(AgentRunResponse response, string? correlationId) => new(null, response, correlationId);

    /// <summary>
    /// Defines the types of entries that can be stored in the durable agent state.
    /// </summary>
    public enum EntryType
    {
        /// <summary>
        /// A user chat message.
        /// </summary>
        ChatMessage,

        /// <summary>
        /// An agent response.
        /// </summary>
        AgentResponse
    }
}
