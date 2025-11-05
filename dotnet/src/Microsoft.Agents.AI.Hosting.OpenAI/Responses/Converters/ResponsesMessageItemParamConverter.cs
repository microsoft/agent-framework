// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ResponsesMessageItemParam that handles role-based polymorphic deserialization.
/// </summary>
internal sealed class ResponsesMessageItemParamConverter : JsonConverter<ResponsesMessageItemParam>
{
    /// <inheritdoc/>
    public override ResponsesMessageItemParam? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var root = doc.RootElement;

        if (!root.TryGetProperty("role", out var roleElement))
        {
            throw new JsonException("ResponsesMessageItemParam must have a 'role' property");
        }

        var role = roleElement.GetString();

        return role switch
        {
            "user" => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesUserMessageItemParam),
            "assistant" => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesAssistantMessageItemParam),
            "system" => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesSystemMessageItemParam),
            "developer" => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesDeveloperMessageItemParam),
            _ => throw new JsonException($"Unknown message role: {role}")
        };
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ResponsesMessageItemParam value, JsonSerializerOptions options)
    {
        switch (value)
        {
            case ResponsesUserMessageItemParam user:
                JsonSerializer.Serialize(writer, user, OpenAIHostingJsonContext.Default.ResponsesUserMessageItemParam);
                break;
            case ResponsesAssistantMessageItemParam assistant:
                JsonSerializer.Serialize(writer, assistant, OpenAIHostingJsonContext.Default.ResponsesAssistantMessageItemParam);
                break;
            case ResponsesSystemMessageItemParam system:
                JsonSerializer.Serialize(writer, system, OpenAIHostingJsonContext.Default.ResponsesSystemMessageItemParam);
                break;
            case ResponsesDeveloperMessageItemParam developer:
                JsonSerializer.Serialize(writer, developer, OpenAIHostingJsonContext.Default.ResponsesDeveloperMessageItemParam);
                break;
            default:
                throw new JsonException($"Unknown message type: {value.GetType().Name}");
        }
    }
}
