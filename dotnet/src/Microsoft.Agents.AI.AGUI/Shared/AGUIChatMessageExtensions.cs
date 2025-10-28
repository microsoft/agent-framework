// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AGUIChatMessageExtensions
{
    private static readonly ChatRole s_developerChatRole = new("developer");

    public static IEnumerable<ChatMessage> AsChatMessages(
        this IEnumerable<AGUIMessage> aguiMessages)
    {
        List<ChatMessage>? result = null;
        foreach (var message in aguiMessages)
        {
            result ??= [];
            var chatMessage = new ChatMessage(
                MapChatRole(message.Role),
                message.Content);

            result.Add(chatMessage);
        }
        return result ?? [];
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages)
    {
        List<AGUIMessage>? result = null;
        foreach (var message in chatMessages)
        {
            result ??= [];
            var aguiMessage = new AGUIMessage
            {
                Id = message.MessageId,
                Role = message.Role.Value,
                Content = message.Text,
            };
            result.Add(aguiMessage);
        }
        return result ?? [];
    }

    public static ChatRole MapChatRole(string role)
    {
        if (string.Equals(role, AGUIRoles.System, StringComparison.OrdinalIgnoreCase))
        {
            return ChatRole.System;
        }
        else if (string.Equals(role, AGUIRoles.User, StringComparison.OrdinalIgnoreCase))
        {
            return ChatRole.User;
        }
        else if (string.Equals(role, AGUIRoles.Assistant, StringComparison.OrdinalIgnoreCase))
        {
            return ChatRole.Assistant;
        }
        else if (string.Equals(role, AGUIRoles.Developer, StringComparison.OrdinalIgnoreCase))
        {
            return s_developerChatRole;
        }

        throw new InvalidOperationException($"Unknown chat role: {role}");
    }
}
