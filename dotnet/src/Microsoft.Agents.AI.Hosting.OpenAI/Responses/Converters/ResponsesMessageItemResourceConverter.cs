// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ResponsesMessageItemResource that handles nested type/role discrimination.
/// </summary>
[ExcludeFromCodeCoverage]
internal sealed class ResponsesMessageItemResourceConverter : JsonConverter<ResponsesMessageItemResource>
{
    /// <inheritdoc/>
    public override ResponsesMessageItemResource? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var root = doc.RootElement;

        if (!root.TryGetProperty("role", out var roleElement))
        {
            throw new JsonException("ResponsesMessageItemResource must have a 'role' property");
        }

        var role = roleElement.GetString();

        // Determine the concrete type based on the role and deserialize using the source generation context
        return role switch
        {
            ResponsesAssistantMessageItemResource.RoleType => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesAssistantMessageItemResource),
            ResponsesUserMessageItemResource.RoleType => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesUserMessageItemResource),
            ResponsesSystemMessageItemResource.RoleType => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesSystemMessageItemResource),
            ResponsesDeveloperMessageItemResource.RoleType => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesDeveloperMessageItemResource),
            _ => throw new JsonException($"Unknown message role: {role}")
        };
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ResponsesMessageItemResource value, JsonSerializerOptions options)
    {
        // Directly serialize using the appropriate type info from the context
        switch (value)
        {
            case ResponsesAssistantMessageItemResource assistant:
                JsonSerializer.Serialize(writer, assistant, OpenAIHostingJsonContext.Default.ResponsesAssistantMessageItemResource);
                break;
            case ResponsesUserMessageItemResource user:
                JsonSerializer.Serialize(writer, user, OpenAIHostingJsonContext.Default.ResponsesUserMessageItemResource);
                break;
            case ResponsesSystemMessageItemResource system:
                JsonSerializer.Serialize(writer, system, OpenAIHostingJsonContext.Default.ResponsesSystemMessageItemResource);
                break;
            case ResponsesDeveloperMessageItemResource developer:
                JsonSerializer.Serialize(writer, developer, OpenAIHostingJsonContext.Default.ResponsesDeveloperMessageItemResource);
                break;
            default:
                throw new JsonException($"Unknown message type: {value.GetType().Name}");
        }
    }
}
