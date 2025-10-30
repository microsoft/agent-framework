// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
        foreach (var message in aguiMessages)
        {
            yield return new ChatMessage(
                MapChatRole(message.Role),
                message.Content);
        }
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages)
    {
        foreach (var message in chatMessages)
        {
            yield return new AGUIMessage
            {
                Id = message.MessageId,
                Role = message.Role.Value,
                Content = message.Text,
            };
        }
    }

    public static ChatRole MapChatRole(string role) =>
        string.Equals(role, AGUIRoles.System, StringComparison.OrdinalIgnoreCase) ? ChatRole.System :
        string.Equals(role, AGUIRoles.User, StringComparison.OrdinalIgnoreCase) ? ChatRole.User :
        string.Equals(role, AGUIRoles.Assistant, StringComparison.OrdinalIgnoreCase) ? ChatRole.Assistant :
        string.Equals(role, AGUIRoles.Developer, StringComparison.OrdinalIgnoreCase) ? s_developerChatRole :
        throw new InvalidOperationException($"Unknown chat role: {role}");
}
