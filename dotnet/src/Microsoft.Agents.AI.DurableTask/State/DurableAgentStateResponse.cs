// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents a durable agent state entry that is a response from the agent.
/// </summary>
internal sealed class DurableAgentStateResponse : DurableAgentStateEntry
{
    /// <summary>
    /// Gets the usage details for this state response.
    /// </summary>
    [JsonPropertyName("usage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DurableAgentStateUsage? Usage { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateResponse"/> from an <see cref="AgentResponse"/>.
    /// </summary>
    /// <param name="correlationId">The correlation ID linking this response to its request.</param>
    /// <param name="response">The <see cref="AgentResponse"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateResponse"/> representing the original response.</returns>
    public static DurableAgentStateResponse FromResponse(string correlationId, AgentResponse response)
    {
        return new DurableAgentStateResponse()
        {
            CorrelationId = correlationId,
            CreatedAt = response.CreatedAt ?? response.Messages.Max(m => m.CreatedAt) ?? DateTimeOffset.UtcNow,
            Messages = response.Messages.Select(DurableAgentStateMessage.FromChatMessage).ToList(),
            Usage = DurableAgentStateUsage.FromUsage(response.Usage)
        };
    }

    /// <summary>
    /// Converts this <see cref="DurableAgentStateResponse"/> back to an <see cref="AgentResponse"/>.
    /// </summary>
    /// <returns>A <see cref="AgentResponse"/> representing this response.</returns>
    public AgentResponse ToResponse()
    {
        return new AgentResponse()
        {
            CreatedAt = this.CreatedAt,
            Messages = this.Messages.Select(m => m.ToChatMessage()).ToList(),
            Usage = this.Usage?.ToUsageDetails(),
        };
    }
}
