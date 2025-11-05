// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the state of a durable agent, including its conversation history.
/// </summary>
public class DurableAgentState
{
    /// <summary>
    /// Gets the ordered list of state entries representing the complete conversation history.
    /// This includes both user messages and agent responses in chronological order.
    /// </summary>
    public List<AgentStateEntry> ConversationHistory { get; set; } = [];

    /// <summary>
    /// Gets all chat messages from the conversation history.
    /// </summary>
    /// <returns>A collection of chat messages in chronological order.</returns>
    public IEnumerable<ChatMessage> EnumerateChatMessages()
    {
        foreach (AgentStateEntry entry in this.ConversationHistory)
        {
            if (entry.Type == AgentStateEntry.EntryType.ChatMessage)
            {
                yield return entry.ChatMessage!;
            }
            else if (entry.Type == AgentStateEntry.EntryType.AgentResponse)
            {
                foreach (ChatMessage message in entry.AgentResponse!.Messages)
                {
                    yield return message;
                }
            }
        }
    }

    /// <summary>
    /// Gets an agent response from the conversation history.
    /// </summary>
    /// <param name="correlationId">The correlation ID of the agent response to get.</param>
    /// <param name="response">The agent response if found, null otherwise.</param>
    /// <returns>True if the agent response was found, false otherwise.</returns>
    public bool TryGetAgentResponse(string correlationId, [NotNullWhen(true)] out AgentRunResponse? response)
    {
        foreach (AgentStateEntry entry in this.ConversationHistory.Where(
            entry => entry.Type == AgentStateEntry.EntryType.AgentResponse &&
            entry.CorrelationId == correlationId))
        {
            response = entry.AgentResponse!;
            return true;
        }

        response = null;
        return false;
    }

    /// <summary>
    /// Adds a chat message to the state.
    /// </summary>
    /// <param name="message">The chat message to add.</param>
    public void AddChatMessage(ChatMessage message)
    {
        this.ConversationHistory.Add(AgentStateEntry.CreateChatMessage(message));
    }

    /// <summary>
    /// Adds an agent response to the state.
    /// </summary>
    /// <param name="response">The agent response to add.</param>
    /// <param name="correlationId">The correlation ID for the agent response.</param>
    public void AddAgentResponse(AgentRunResponse response, string? correlationId)
    {
        this.ConversationHistory.Add(AgentStateEntry.CreateAgentResponse(response, correlationId));
    }
}
