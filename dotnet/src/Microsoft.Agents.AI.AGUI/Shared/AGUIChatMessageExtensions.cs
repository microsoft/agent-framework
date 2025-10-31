// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
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
        this IEnumerable<AGUIMessage> aguiMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        foreach (var message in aguiMessages)
        {
            var role = MapChatRole(message.Role);

            if (role == ChatRole.Tool && message.CallId is not null)
            {
                object? content = message.Content;
                if (!string.IsNullOrEmpty(message.Content))
                {
                    var typeInfo = jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)) as System.Text.Json.Serialization.Metadata.JsonTypeInfo<JsonElement>;
                    content = JsonSerializer.Deserialize(message.Content, typeInfo!);
                }

                yield return new ChatMessage(
                    role,
                    [new FunctionResultContent(message.CallId, content)]);
            }
            else
            {
                yield return new ChatMessage(role, message.Content);
            }
        }
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        foreach (var message in chatMessages)
        {
            // Check if this is a tool result message
            if (message.Role == ChatRole.Tool)
            {
                FunctionResultContent? functionResult = null;
                foreach (var content in message.Contents)
                {
                    if (content is FunctionResultContent frc)
                    {
                        functionResult = frc;
                        break;
                    }
                }

                if (functionResult is not null)
                {
                    string contentJson = string.Empty;
                    if (functionResult.Result is not null)
                    {
                        var typeInfo = jsonSerializerOptions.TypeInfoResolver?.GetTypeInfo(functionResult.Result.GetType(), jsonSerializerOptions)
                            ?? throw new InvalidOperationException("TypeInfoResolver must be configured for AOT-compatible serialization.");
                        contentJson = JsonSerializer.Serialize(functionResult.Result, typeInfo);
                    }

                    yield return new AGUIMessage
                    {
                        Id = message.MessageId,
                        Role = AGUIRoles.Tool,
                        Content = contentJson,
                        CallId = functionResult.CallId,
                    };
                    continue;
                }
            }

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
        string.Equals(role, AGUIRoles.Tool, StringComparison.OrdinalIgnoreCase) ? ChatRole.Tool :
        throw new InvalidOperationException($"Unknown chat role: {role}");
}
