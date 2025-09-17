// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="Message"/> class.
/// </summary>
internal static class A2AMessageExtensions
{
    /// <summary>
    /// Converts an A2A <see cref="Message"/> to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="message">The A2A message to convert.</param>
    /// <param name="authorName">The author name to set on the resulting <see cref="ChatMessage"/>.</param>
    /// <returns>The corresponding <see cref="ChatMessage"/>.</returns>
    public static ChatMessage ToChatMessage(this Message message, string? authorName = null)
    {
        List<AIContent>? aiContents = null;

        foreach (var part in message.Parts)
        {
            (aiContents ??= []).Add(part.ToAIContent());
        }

        return new ChatMessage(ChatRole.Assistant, aiContents)
        {
            MessageId = message.MessageId,
            AuthorName = authorName,
            Role = message.Role == MessageRole.Agent ? ChatRole.Assistant : ChatRole.User,
            AdditionalProperties = message.Metadata.ToAdditionalProperties(),
            RawRepresentation = message,
        };
    }
}
