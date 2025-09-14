// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using A2A;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A.Converters;

internal static class MessageConverter
{
    public static List<Part> ToParts(this IList<ChatMessage> chatMessages)
    {
        if (chatMessages is null || chatMessages.Count == 0)
        {
            return [];
        }

        var parts = new List<Part>();
        foreach (var chatMessage in chatMessages)
        {
            foreach (var content in chatMessage.Contents)
            {
                var part = ConvertAIContentToPart(content);
                if (part is not null)
                {
                    parts.Add(part);
                }
            }

            // If no parts were created from content, create a text part from the message text
            if (chatMessage.Contents.Count == 0 && !string.IsNullOrEmpty(chatMessage.Text))
            {
                parts.Add(new TextPart { Text = chatMessage.Text });
            }
        }

        return parts;
    }

    /// <summary>
    /// Converts A2A MessageSendParams to a collection of Microsoft.Extensions.AI ChatMessage objects.
    /// </summary>
    /// <param name="messageSendParams">The A2A message send parameters to convert.</param>
    /// <returns>A read-only collection of ChatMessage objects.</returns>
    public static List<ChatMessage> ToChatMessages(this MessageSendParams messageSendParams)
    {
        if (messageSendParams is null)
        {
            return [];
        }

        var result = new List<ChatMessage>();
        if (messageSendParams.Message?.Parts is not null)
        {
            var chatMessage = ToChatMessage(messageSendParams.Message);
            if (chatMessage is not null)
            {
                result.Add(chatMessage);
            }
        }

        return result;
    }

    /// <summary>
    /// Converts collection of A2A <see cref="Message"/> to a collection of <see cref="ChatMessage"/> objects.
    /// </summary>
    /// <returns>A read-only collection of ChatMessage objects.</returns>
    public static IReadOnlyCollection<ChatMessage> ToChatMessages(this ICollection<Message> messages)
    {
        if (messages is null || messages.Count == 0)
        {
            return [];
        }

        var result = new List<ChatMessage>();
        foreach (var message in messages)
        {
            var chatMessage = ToChatMessage(message);
            if (chatMessage is not null)
            {
                result.Add(chatMessage);
            }
        }

        return result;
    }

    /// <summary>
    /// Converts a single <see cref="Message"/> to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="message">The A2A message to convert.</param>
    /// <returns>A ChatMessage object, or null if conversion is not possible.</returns>
    public static ChatMessage? ToChatMessage(this Message message)
    {
        if (message?.Parts is not { Count: > 0 })
        {
            return null;
        }

        var chatRole = ConvertMessageRoleToChatRole(message.Role);

        var content = new List<AIContent>();
        foreach (var part in message.Parts)
        {
            var aiContent = ConvertPartToAIContent(part);
            if (aiContent is not null)
            {
                content.Add(aiContent);
            }
        }

        // If no valid content was extracted, return null
        if (content.Count == 0)
        {
            return null;
        }

        // Create the ChatMessage with appropriate metadata
        var chatMessage = new ChatMessage(chatRole, content)
        {
            MessageId = message.MessageId,
            RawRepresentation = message
        };

        // Add any additional properties if needed
        if (message.Metadata is not null)
        {
            chatMessage.AdditionalProperties = message.Metadata.ToAdditionalPropertiesDictionary();
        }

        return chatMessage;
    }

    /// <summary>
    /// Converts A2A MessageRole to Microsoft.Extensions.AI ChatRole.
    /// </summary>
    /// <param name="messageRole">The A2A message role.</param>
    /// <returns>The corresponding ChatRole.</returns>
    private static ChatRole ConvertMessageRoleToChatRole(MessageRole messageRole) => messageRole switch
    {
        MessageRole.User => ChatRole.User,
        MessageRole.Agent => ChatRole.Assistant,
        _ => ChatRole.User
    };

    /// <summary>
    /// Converts an A2A Part to Microsoft.Extensions.AI AIContent.
    /// </summary>
    /// <param name="part">The A2A part to convert.</param>
    /// <returns>An AIContent object, or null if conversion is not possible.</returns>
#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private static AIContent? ConvertPartToAIContent(Part part) =>
        part switch
        {
            TextPart textPart => new TextContent(textPart.Text)
            {
                RawRepresentation = textPart,
                AdditionalProperties = textPart.Metadata?.ToAdditionalPropertiesDictionary()
            },
            FilePart or DataPart or _ => throw new NotSupportedException($"Part type '{part.GetType().Name}' is not supported. Only TextPart is supported.")
        };

    /// <summary>
    /// Converts Microsoft.Extensions.AI ChatMessage back to A2A Message format.
    /// This is useful for the reverse operation.
    /// </summary>
    /// <param name="chatMessage">The ChatMessage to convert.</param>
    /// <returns>An A2A Message object.</returns>
    public static Message ToA2AMessage(this ChatMessage chatMessage)
    {
        if (chatMessage is null)
        {
            throw new ArgumentNullException(nameof(chatMessage));
        }

        var message = new Message
        {
            MessageId = chatMessage.MessageId ?? Guid.NewGuid().ToString(),
            Role = ConvertChatRoleToMessageRole(chatMessage.Role),
            Parts = []
        };

        // Convert content to parts
        foreach (var content in chatMessage.Contents)
        {
            var part = ConvertAIContentToPart(content);
            if (part is not null)
            {
                message.Parts.Add(part);
            }
        }

        // If no parts were created from content, create a text part from the message text
        if (message.Parts.Count == 0 && !string.IsNullOrEmpty(chatMessage.Text))
        {
            message.Parts.Add(new TextPart { Text = chatMessage.Text });
        }

        return message;
    }

    /// <summary>
    /// Converts Microsoft.Extensions.AI ChatRole to A2A MessageRole.
    /// </summary>
    /// <param name="chatRole">The ChatRole to convert.</param>
    /// <returns>The corresponding MessageRole.</returns>
    private static MessageRole ConvertChatRoleToMessageRole(ChatRole chatRole)
    {
        if (chatRole == ChatRole.User)
        {
            return MessageRole.User;
        }
        if (chatRole == ChatRole.Assistant)
        {
            return MessageRole.Agent;
        }

        return MessageRole.User; // Default fallback
    }

    /// <summary>
    /// Converts Microsoft.Extensions.AI AIContent to A2A Part.
    /// </summary>
    /// <param name="content">The AIContent to convert.</param>
    /// <returns>A Part object, or null if conversion is not possible.</returns>
#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private static Part? ConvertAIContentToPart(AIContent content) =>
        content switch
        {
            TextContent textContent => new TextPart
            {
                Text = textContent.Text
            },
            _ => throw new NotSupportedException($"Content type '{content.GetType().Name}' is not supported.")
        };

    private static AdditionalPropertiesDictionary? ToAdditionalPropertiesDictionary(this Dictionary<string, JsonElement> metadata)
    {
        if (metadata is not { Count: > 0 })
        {
            return null;
        }

        var additionalProperties = new AdditionalPropertiesDictionary();
        foreach (var kvp in metadata)
        {
            additionalProperties[kvp.Key] = kvp.Value;
        }
        return additionalProperties;
    }
}
