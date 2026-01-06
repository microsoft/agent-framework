// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal static class AIAgentsAbstractionsExtensions
{
    public static ChatMessage ToChatMessage(this AgentResponseUpdate update) =>
        new()
        {
            AuthorName = update.AuthorName,
            Contents = update.Contents,
            Role = update.Role ?? ChatRole.User,
            CreatedAt = update.CreatedAt,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation ?? update,
        };

    public static ChatMessage ChatAssistantToUserIfNotFromNamed(this ChatMessage message, string agentName)
        => message.ChatAssistantToUserIfNotFromNamed(agentName, out _, false);

    private static ChatMessage ChatAssistantToUserIfNotFromNamed(this ChatMessage message, string agentName, out bool changed, bool inplace = true)
    {
        changed = false;

        if (message.Role == ChatRole.Assistant &&
                message.AuthorName != agentName &&
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

    /// <summary>
    /// Iterates through <paramref name="messages"/> looking for <see cref="ChatRole.Assistant"/> messages and swapping
    /// any that have a different <see cref="ChatMessage.AuthorName"/> from <paramref name="targetAgentName"/> to
    /// <see cref="ChatRole.User"/>.
    /// </summary>
    public static List<ChatMessage>? ChangeAssistantToUserForOtherParticipants(this List<ChatMessage> messages, string targetAgentName)
    {
        List<ChatMessage>? roleChanged = null;
        foreach (var m in messages)
        {
            m.ChatAssistantToUserIfNotFromNamed(targetAgentName, out bool changed);
            if (changed)
            {
                (roleChanged ??= []).Add(m);
            }
        }

        return roleChanged;
    }

    /// <summary>
    /// Undoes changes made by <see cref="ChangeAssistantToUserForOtherParticipants"/> when passed the list of changes
    /// made by that method.
    /// </summary>
    public static void ResetUserToAssistantForChangedRoles(this List<ChatMessage>? roleChanged)
    {
        if (roleChanged is not null)
        {
            foreach (var m in roleChanged)
            {
                m.Role = ChatRole.Assistant;
            }
        }
    }
}
