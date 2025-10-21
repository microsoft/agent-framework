// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.A2A.Converters;

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
            result.Add(messageSendParams.Message.ToChatMessage());
        }

        return result;
    }
}
