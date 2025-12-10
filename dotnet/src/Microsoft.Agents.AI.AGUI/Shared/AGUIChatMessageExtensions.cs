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

            switch (message)
            {
                case AGUIToolMessage toolMessage:
                {
                    object? result;
                    if (string.IsNullOrEmpty(toolMessage.Content))
                    {
                        result = toolMessage.Content;
                    }
                    else
                    {
                        // Try to deserialize as JSON, but fall back to string if it fails
                        try
                        {
                            result = JsonSerializer.Deserialize(toolMessage.Content, AGUIJsonSerializerContext.Default.JsonElement);
                        }
                        catch (JsonException)
                        {
                            result = toolMessage.Content;
                        }
                    }

                    yield return new ChatMessage(
                        role,
                        [
                            new FunctionResultContent(
                                    toolMessage.ToolCallId,
                                    result)
                        ]);
                    break;
                }

                case AGUIAssistantMessage assistantMessage when assistantMessage.ToolCalls is { Length: > 0 }:
                {
                    var contents = new List<AIContent>();

                    if (!string.IsNullOrEmpty(assistantMessage.Content))
                    {
                        contents.Add(new TextContent(assistantMessage.Content));
                    }

                    // Add tool calls
                    foreach (var toolCall in assistantMessage.ToolCalls)
                    {
                        Dictionary<string, object?>? arguments = null;
                        if (!string.IsNullOrEmpty(toolCall.Function.Arguments))
                        {
                            arguments = (Dictionary<string, object?>?)JsonSerializer.Deserialize(
                                toolCall.Function.Arguments,
                                jsonSerializerOptions.GetTypeInfo(typeof(Dictionary<string, object?>)));
                        }

                        contents.Add(new FunctionCallContent(
                            toolCall.Id,
                            toolCall.Function.Name,
                            arguments));
                    }

                    yield return new ChatMessage(role, contents)
                    {
                        MessageId = message.Id
                    };
                    break;
                }

                default:
                {
                    string content = message switch
                    {
                        AGUIDeveloperMessage dev => dev.Content,
                        AGUISystemMessage sys => sys.Content,
                        AGUIUserMessage user => user.Content,
                        AGUIAssistantMessage asst => asst.Content,
                        _ => string.Empty
                    };

                    yield return new ChatMessage(role, content)
                    {
                        MessageId = message.Id
                    };
                    break;
                }
            }
        }
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        foreach (var message in chatMessages)
        {
            message.MessageId ??= Guid.NewGuid().ToString("N");
            if (message.Role == ChatRole.Tool)
            {
                foreach (var toolMessage in MapToolMessages(jsonSerializerOptions, message))
                {
                    yield return toolMessage;
                }
            }
            else if (message.Role == ChatRole.Assistant)
            {
                var assistantMessage = MapAssistantMessage(jsonSerializerOptions, message);
                if (assistantMessage != null)
                {
                    yield return assistantMessage;
                }
            }
            else
            {
                yield return message.Role.Value switch
                {
                    AGUIRoles.Developer => new AGUIDeveloperMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                    AGUIRoles.System => new AGUISystemMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                    AGUIRoles.User => new AGUIUserMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                    _ => throw new InvalidOperationException($"Unknown role: {message.Role.Value}")
                };
            }
        }
    }

    private static AGUIAssistantMessage? MapAssistantMessage(JsonSerializerOptions jsonSerializerOptions, ChatMessage message)
    {
        List<AGUIToolCall>? toolCalls = null;
        string? textContent = null;

        foreach (var content in message.Contents)
        {
            if (content is FunctionCallContent functionCall)
            {
                var argumentsJson = functionCall.Arguments is null ?
                    "{}" :
                    JsonSerializer.Serialize(functionCall.Arguments, jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)));
                toolCalls ??= [];
                toolCalls.Add(new AGUIToolCall
                {
                    Id = functionCall.CallId,
                    Type = "function",
                    Function = new AGUIFunctionCall
                    {
                        Name = functionCall.Name,
                        Arguments = argumentsJson
                    }
                });
            }
            else if (content is TextContent textContentItem)
            {
                textContent = textContentItem.Text;
            }
        }

        // Create message with tool calls and/or text content
        if (toolCalls?.Count > 0 || !string.IsNullOrEmpty(textContent))
        {
            return new AGUIAssistantMessage
            {
                Id = message.MessageId,
                Content = textContent ?? string.Empty,
                ToolCalls = toolCalls?.Count > 0 ? toolCalls.ToArray() : null
            };
        }

        return null;
    }

    private static IEnumerable<AGUIToolMessage> MapToolMessages(JsonSerializerOptions jsonSerializerOptions, ChatMessage message)
    {
        foreach (var content in message.Contents)
        {
            if (content is FunctionResultContent functionResult)
            {
                yield return new AGUIToolMessage
                {
                    Id = functionResult.CallId,
                    ToolCallId = functionResult.CallId,
                    Content = functionResult.Result is null ?
                        string.Empty :
                        JsonSerializer.Serialize(functionResult.Result, jsonSerializerOptions.GetTypeInfo(functionResult.Result.GetType()))
                };
            }
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
