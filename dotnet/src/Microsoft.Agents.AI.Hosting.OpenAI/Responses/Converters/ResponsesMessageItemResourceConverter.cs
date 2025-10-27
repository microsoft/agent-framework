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
    private readonly ResponsesJsonContext _context;

    /// <summary>
    /// Initializes a new instance of the <see cref="ResponsesMessageItemResourceConverter"/> class.
    /// </summary>
    public ResponsesMessageItemResourceConverter()
    {
        this._context = ResponsesJsonContext.Default;
    }

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
                    // Skip nested objects/arrays
                    readerClone.Skip();
                }
            }
        }

        // Determine the concrete type based on the role and deserialize using the source generation context
        return role switch
        {
            ResponsesAssistantMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, this._context.ResponsesAssistantMessageItemResource),
            ResponsesUserMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, this._context.ResponsesUserMessageItemResource),
            ResponsesSystemMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, this._context.ResponsesSystemMessageItemResource),
            ResponsesDeveloperMessageItemResource.RoleType => JsonSerializer.Deserialize(ref reader, this._context.ResponsesDeveloperMessageItemResource),
            _ => throw new JsonException($"Unknown message role: {role}")
        };
    }

    public override void Write(Utf8JsonWriter writer, ResponsesMessageItemResource value, JsonSerializerOptions options)
    {
        // Directly serialize using the appropriate type info from the context
        switch (value)
        {
            case ResponsesAssistantMessageItemResource assistant:
                JsonSerializer.Serialize(writer, assistant, this._context.ResponsesAssistantMessageItemResource);
                break;
            case ResponsesUserMessageItemResource user:
                JsonSerializer.Serialize(writer, user, this._context.ResponsesUserMessageItemResource);
                break;
            case ResponsesSystemMessageItemResource system:
                JsonSerializer.Serialize(writer, system, this._context.ResponsesSystemMessageItemResource);
                break;
            case ResponsesDeveloperMessageItemResource developer:
                JsonSerializer.Serialize(writer, developer, this._context.ResponsesDeveloperMessageItemResource);
                break;
            default:
                throw new JsonException($"Unknown message type: {value.GetType().Name}");
        }
    }
}
