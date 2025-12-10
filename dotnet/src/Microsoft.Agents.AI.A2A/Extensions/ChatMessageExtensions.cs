// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for the <see cref="ChatMessage"/> class.
/// </summary>
internal static class ChatMessageExtensions
{
    internal static AgentMessage ToA2AMessage(this IEnumerable<ChatMessage> messages)
    {
        List<Part> allParts = [];

        foreach (var message in messages)
        {
            if (message.Contents.ToParts() is { Count: > 0 } ps)
            {
                allParts.AddRange(ps);
            }
        }

        return new AgentMessage
        {
            MessageId = Guid.NewGuid().ToString("N"),
            Role = MessageRole.User,
            Parts = allParts,
        };
    }
}
