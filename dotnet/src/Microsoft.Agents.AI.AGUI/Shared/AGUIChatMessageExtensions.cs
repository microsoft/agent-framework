// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
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

            if (message is AGUIToolMessage toolMessage)
            {
                object? content = toolMessage.Content;
                if (!string.IsNullOrEmpty(toolMessage.Content))
                {
                    content = JsonSerializer.Deserialize(toolMessage.Content, AGUIJsonSerializerContext.Default.JsonElement);
                }

                yield return new ChatMessage(
                    role,
                    [new FunctionResultContent(toolMessage.ToolCallId, content)]);
            }
            else if (message is AGUIAssistantMessage assistantMessage && assistantMessage.ToolCalls is { Length: > 0 })
            {
                // Assistant message with tool calls
                var contents = new List<AIContent>();

                // Add text content if present
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
                        // Parse arguments as Dictionary<string, JsonElement?>
                        var typeInfo = jsonSerializerOptions.GetTypeInfo(typeof(Dictionary<string, JsonElement?>)) as JsonTypeInfo<Dictionary<string, JsonElement?>>;
                        var jsonArgs = JsonSerializer.Deserialize(toolCall.Function.Arguments, typeInfo!);

                        if (jsonArgs is not null)
                        {
                            // Convert to Dictionary<string, object?>
                            arguments = new Dictionary<string, object?>(jsonArgs.Count);
                            foreach (var kvp in jsonArgs)
                            {
                                arguments[kvp.Key] = kvp.Value;
                            }
                        }
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
            }
            else
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
            }
        }
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        foreach (var message in chatMessages)
        {
            message.MessageId ??= Guid.NewGuid().ToString();
            // Check if this is a tool result message
            if (message.Role == ChatRole.Tool)
            {
                FunctionResultContent? functionResult = null;
                foreach (var content in message.Contents)
                {
                    if (content is FunctionResultContent frc)
                    {
                        if (functionResult is not null)
                        {
                            throw new InvalidOperationException("A tool message should contain only one FunctionResultContent.");
                        }
                        functionResult = frc;
                    }
                }

                if (functionResult is not null)
                {
                    string contentJson = string.Empty;
                    if (functionResult.Result is not null)
                    {
                        // Convert the result to JsonElement for AOT-compatible serialization
                        JsonElement resultElement = ConvertToJsonElement(functionResult.Result, jsonSerializerOptions);
                        // JsonElement has a built-in GetRawText() method that returns the JSON string representation
                        contentJson = resultElement.GetRawText();
                    }

                    yield return new AGUIToolMessage
                    {
                        Id = message.MessageId,
                        ToolCallId = functionResult.CallId,
                        Content = contentJson,
                    };
                    continue;
                }
            }

            // Check if this is an assistant message with tool calls
            if (message.Role == ChatRole.Assistant)
            {
                var toolCalls = new List<AGUIToolCall>();
                string? textContent = null;

                // Extract tool calls and text content
                foreach (var content in message.Contents)
                {
                    if (content is FunctionCallContent functionCall)
                    {
                        // Serialize arguments to JSON string
                        string argumentsJson = "{}";
                        if (functionCall.Arguments is not null)
                        {
                            var typeInfo = jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)) as JsonTypeInfo<IDictionary<string, object?>>;
                            argumentsJson = JsonSerializer.Serialize(functionCall.Arguments, typeInfo!);
                        }

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
                if (toolCalls.Count > 0 || !string.IsNullOrEmpty(textContent))
                {
                    yield return new AGUIAssistantMessage
                    {
                        Id = message.MessageId,
                        Content = textContent ?? string.Empty,
                        ToolCalls = toolCalls.Count > 0 ? toolCalls.ToArray() : null
                    };
                    continue;
                }
            }

            yield return message.Role.Value switch
            {
                AGUIRoles.Developer => new AGUIDeveloperMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                AGUIRoles.System => new AGUISystemMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                AGUIRoles.User => new AGUIUserMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                AGUIRoles.Assistant => new AGUIAssistantMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                _ => throw new InvalidOperationException($"Unknown role: {message.Role.Value}")
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

    private static JsonElement ConvertToJsonElement(object value, JsonSerializerOptions jsonSerializerOptions)
    {
        // If already a JsonElement, return it directly
        if (value is JsonElement element)
        {
            return element;
        }

        // If it's a dictionary with object values, convert to Dictionary<string, JsonElement>
        if (value is IDictionary<string, object?> dict)
        {
            var elementDict = new Dictionary<string, JsonElement>(dict.Count);
            foreach (var kvp in dict)
            {
                if (kvp.Value is null)
                {
                    elementDict[kvp.Key] = default;
                }
                else
                {
                    // Recursively convert each value to JsonElement
                    elementDict[kvp.Key] = ConvertToJsonElement(kvp.Value, jsonSerializerOptions);
                }
            }

            return JsonSerializer.SerializeToElement(elementDict, AGUIJsonSerializerContext.Default.DictionaryStringJsonElement);
        }

        var typeInfo = jsonSerializerOptions.GetTypeInfo(value.GetType());
        if (typeInfo is not null)
        {
            return JsonSerializer.SerializeToElement(value, typeInfo);
        }

        // Fallback: if no TypeInfoResolver, throw an exception
        throw new InvalidOperationException("TypeInfoResolver must be configured for AOT-compatible serialization of tool results.");
    }
}
