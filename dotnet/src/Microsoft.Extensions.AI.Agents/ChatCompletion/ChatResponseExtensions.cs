// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Contains extension methods for <see cref="ChatResponse"/> and <see cref="ChatResponseUpdate"/>.
/// </summary>
internal static class ChatResponseExtensions
{
    /// <summary>
    /// Converts a <see cref="ChatResponse"/> instance to an <see cref="AgentRunResponse"/>.
    /// </summary>
    /// <param name="chatResponse">The <see cref="ChatResponse"/> to convert. Cannot be <see langword="null"/>.</param>
    /// <param name="agentId">The ID of the agent that generated the response. Cannot be <see langword="null"/>.</param>
    /// <returns>
    /// An <see cref="AgentRunResponse"/> containing the messages, metadata, and additional properties from the
    /// specified <see cref="ChatResponse"/>.
    /// </returns>
    public static AgentRunResponse ToAgentRunResponse(this ChatResponse chatResponse, string agentId)
    {
        _ = Throw.IfNull(chatResponse);
        _ = Throw.IfNullOrWhitespace(agentId);

        return new AgentRunResponse(chatResponse.Messages)
        {
            AgentId = agentId,
            ResponseId = chatResponse.ResponseId,
            CreatedAt = chatResponse.CreatedAt,
            Usage = chatResponse.Usage,
            RawRepresentation = chatResponse,
            AdditionalProperties = chatResponse.AdditionalProperties
        };
    }

    /// <summary>
    /// Converts a <see cref="ChatResponseUpdate"/> instance to an <see cref="AgentRunResponseUpdate"/>.
    /// </summary>
    /// <param name="chatResponseUpdate">The <see cref="ChatResponseUpdate"/> to convert. Cannot be <see langword="null"/>.</param>
    /// <param name="agentId">The ID of the agent that generated the response. Cannot be <see langword="null"/>.</param>
    /// <returns>An <see cref="AgentRunResponseUpdate"/> containing the properties from the specified <see cref="ChatResponseUpdate"/>.</returns>
    public static AgentRunResponseUpdate ToAgentRunResponseUpdate(this ChatResponseUpdate chatResponseUpdate, string agentId)
    {
        _ = Throw.IfNull(chatResponseUpdate);

        return new()
        {
            AgentId = agentId,
            Role = chatResponseUpdate.Role,
            AuthorName = chatResponseUpdate.AuthorName,
            Contents = chatResponseUpdate.Contents,
            MessageId = chatResponseUpdate.MessageId,
            ResponseId = chatResponseUpdate.ResponseId,
            CreatedAt = chatResponseUpdate.CreatedAt,
            RawRepresentation = chatResponseUpdate,
            AdditionalProperties = chatResponseUpdate.AdditionalProperties
        };
    }
}
