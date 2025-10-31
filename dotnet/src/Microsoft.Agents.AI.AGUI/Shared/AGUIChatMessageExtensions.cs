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

            if (role == ChatRole.Tool && message.CallId is not null)
            {
                object? content = message.Content;
                if (!string.IsNullOrEmpty(message.Content))
                {
                    content = JsonSerializer.Deserialize(message.Content, AGUIJsonSerializerContext.Default.JsonElement);
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
                        // Convert the result to JsonElement for AOT-compatible serialization
                        JsonElement resultElement = ConvertToJsonElement(functionResult.Result, jsonSerializerOptions);
                        // JsonElement has a built-in GetRawText() method that returns the JSON string representation
                        contentJson = resultElement.GetRawText();
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
            // Serialize the Dictionary<string, JsonElement> which is AOT-compatible
            string json = JsonSerializer.Serialize(elementDict, AGUIJsonSerializerContext.Default.DictionaryStringJsonElement);
            using JsonDocument doc = JsonDocument.Parse(json);
            return doc.RootElement.Clone();
        }

        // For primitive types and other objects, serialize to a document and extract the root element
        // This handles int, string, bool, arrays, etc.
        JsonTypeInfo? typeInfo = jsonSerializerOptions.TypeInfoResolver?.GetTypeInfo(value.GetType(), jsonSerializerOptions);
        if (typeInfo is not null)
        {
            string json = JsonSerializer.Serialize(value, typeInfo);
            using JsonDocument doc = JsonDocument.Parse(json);
            return doc.RootElement.Clone();
        }

        // Fallback: if no TypeInfoResolver, throw an exception
        throw new InvalidOperationException("TypeInfoResolver must be configured for AOT-compatible serialization of tool results.");
    }
}
