// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.A2A.Converters;

internal static class MessageConverter
{
    public static List<Part> ToParts(this AgentResponseUpdate update)
    {
        if (update is null || update.Contents is not { Count: > 0 })
        {
            return [];
        }

        var parts = new List<Part>();
        foreach (var content in update.Contents)
        {
            var part = content.ToPart();
            if (part is not null)
            {
                parts.Add(part);
            }
        }

        return parts;
    }

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
                var part = content.ToPart();
                if (part is not null)
                {
                    parts.Add(part);
                }
            }
        }

        return parts;
    }
    /// <summary>
    /// Converts A2A SendMessageRequest to a collection of Microsoft.Extensions.AI ChatMessage objects.
    /// </summary>
    /// <param name="sendMessageRequest">The A2A send message request to convert.</param>
    /// <returns>A read-only collection of ChatMessage objects.</returns>
    public static List<ChatMessage> ToChatMessages(this SendMessageRequest sendMessageRequest)
    {
        if (sendMessageRequest is null)
        {
            return [];
        }

        var result = new List<ChatMessage>();
        if (sendMessageRequest.Message?.Parts is not null)
        {
            result.Add(sendMessageRequest.Message.ToChatMessage());
        }

        return result;
    }
}
