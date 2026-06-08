// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal static class AIAgentsAbstractionsExtensions
{
    public static ChatMessage ChatAssistantToUserIfNotFromNamed(this ChatMessage message, string agentName)
        => message.ChatAssistantToUserIfNotFromNamed(agentName, out _, false);

    private static ChatMessage ChatAssistantToUserIfNotFromNamed(this ChatMessage message, string agentName, out bool changed, bool inplace = true)
    {
        changed = false;

        if (message.Role == ChatRole.Assistant &&
            !StringComparer.Ordinal.Equals(message.AuthorName, agentName) &&
            message.Contents.All(c => c is TextContent or DataContent or UriContent or UsageContent))
        {
            if (!inplace)
            {
                message = message.Clone();
            }

            message.Role = ChatRole.User;
            changed = true;
        }

        return message;
    }

    public static List<ChatMessage> CopyWithAssistantToUserForOtherParticipants(
        this IEnumerable<ChatMessage> messages,
        string targetAgentName)
        => messages.Select(m => m.ChatAssistantToUserIfNotFromNamed(targetAgentName, out _, false)).ToList();
}
