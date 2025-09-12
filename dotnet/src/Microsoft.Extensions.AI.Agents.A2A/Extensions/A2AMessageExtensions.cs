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
    /// Converts a list of A2A <see cref="Message"/> to a list of <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="messages">The A2A messages to convert.</param>
    /// <param name="authorName">The author name to set on the resulting <see cref="ChatMessage"/>.</param>
    /// <param name="artifacts">The A2A artifacts to convert and add as chat messages.</param>
    /// <returns>The corresponding list of <see cref="ChatMessage"/>.</returns>
    internal static IList<ChatMessage> ToChatMessages(this IList<Message> messages, string? authorName = null, IList<Artifact>? artifacts = null)
    {
        List<ChatMessage> chatMessages = new(messages.Count);

        foreach (var message in messages)
        {
            chatMessages.Add(message.ToChatMessage(authorName));
        }

        // TBD: Decide how to represent artifacts. Add them after the messages created from the task history messages,
        // before them or instead of them, or, maybe allow to configure the behavior via A2AAgentOptions?
        if (artifacts is { Count: > 0 })
        {
            foreach (var artifact in artifacts)
            {
                chatMessages.Add(artifact.ToChatMessage(authorName));
            }
        }

        return chatMessages;
    }

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
