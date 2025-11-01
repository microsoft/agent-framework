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
        // Clone the reader to peek at the JSON
        Utf8JsonReader readerClone = reader;

        // Read through the JSON to find the role property
        string? role = null;

        if (readerClone.TokenType != JsonTokenType.StartObject)
        {
            throw new JsonException("Expected start of object");
        }

        while (readerClone.Read())
        {
            if (readerClone.TokenType == JsonTokenType.EndObject)
            {
                break;
            }

            if (readerClone.TokenType == JsonTokenType.PropertyName)
            {
                string propertyName = readerClone.GetString()!;
                readerClone.Read(); // Move to the value

                if (propertyName == "role")
                {
                    role = readerClone.GetString();
                    break;
                }

                if (readerClone.TokenType is JsonTokenType.StartObject or JsonTokenType.StartArray)
                {
                    // The Utf8JsonReader.Skip() method will fail fast if it detects that we're reading
                    // from a partially read buffer, regardless of whether the next value is available.
                    // This can result in erroneous failures in cases where a custom converter is calling
                    // into a built-in converter (cf. https://github.com/dotnet/runtime/issues/74108).
                    // For this reason we need to call the TrySkip() method instead -- the serializer
                    // should guarantee sufficient read-ahead has been performed for the current object.
                    if (!readerClone.TrySkip())
                    {
                        throw new InvalidOperationException("Failed to skip nested JSON value. Serializer should guarantee sufficient read-ahead has been done.");
                    }
                }
            }
        }

        // Determine the concrete type based on the role and deserialize using the source generation context
        return role switch
        {
            ResponsesAssistantMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ResponsesAssistantMessageItemResource),
            ResponsesUserMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ResponsesUserMessageItemResource),
            ResponsesSystemMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ResponsesSystemMessageItemResource),
            ResponsesDeveloperMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ResponsesDeveloperMessageItemResource),
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
