// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Utils;

internal static class AgentRunResponseUpdateExtensions
{
    /// <summary>
    /// Converts an <see cref="AgentRunResponseUpdate"/> instance to a <see cref="ChatResponse"/>.
    /// </summary>
    /// <param name="response">The <see cref="AgentRunResponse"/> to convert. Cannot be null.</param>
    /// <param name="role">The role of agent run response contents. By default is <see cref="ChatRole.Assistant"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> populated with values from <paramref name="response"/>.</returns>
    public static ChatResponse AsChatResponse(this AgentRunResponseUpdate response, ChatRole? role = null) => new()
    {
        CreatedAt = response.CreatedAt,
        ResponseId = response.ResponseId,
        RawRepresentation = response.RawRepresentation,
        AdditionalProperties = response.AdditionalProperties,
        Messages = [new ChatMessage(response.Role ?? role ?? ChatRole.Assistant, response.Contents)]
    };
}
