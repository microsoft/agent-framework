// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides utility methods for wrapping array types in ChatResponseFormat to comply with OpenAI's structured output requirements.
/// </summary>
internal static class ChatResponseFormatArrayWrapper
{
    /// <summary>
    /// Wraps array types in a container object with a 'data' property to satisfy OpenAI's requirement
    /// that the root schema must be an object, not an array.
    /// </summary>
    /// <param name="responseFormat">The response format to potentially wrap.</param>
    /// <returns>
    /// A wrapped response format if the original was for an array type, otherwise the original response format.
    /// </returns>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning disable CA1869 // Avoid creating a new 'JsonSerializerOptions' instance for every serialization operation
    public static ChatResponseFormat? WrapArrayTypeIfNeeded(ChatResponseFormat? responseFormat)
    {
        if (responseFormat is null)
        {
            return null;
        }

        // Check if this is a JSON schema format with an array root type
        if (!IsArraySchemaFormat(responseFormat, out JsonElement schemaElement, out string? schemaName, out string? schemaDescription))
        {
            // Not an array schema, return as-is
            return responseFormat;
        }

        // Create a new object schema that wraps the array
        var wrappedSchema = new Dictionary<string, object>
        {
            ["type"] = "object",
            ["properties"] = new Dictionary<string, object>
            {
                ["data"] = schemaElement
            },
            ["additionalProperties"] = false,
            ["required"] = new[] { "data" }
        };

        // Add $schema property if it exists in the original
        if (schemaElement.TryGetProperty("$schema", out JsonElement schemaUri))
        {
            wrappedSchema["$schema"] = schemaUri.GetString()!;
        }

        // Serialize to JsonElement
#if NET
        var serializerOptions = new JsonSerializerOptions
        {
            TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver()
        };
        string wrappedSchemaJson = JsonSerializer.Serialize(wrappedSchema, serializerOptions);
#else
        string wrappedSchemaJson = JsonSerializer.Serialize(wrappedSchema);
#endif
        JsonElement wrappedSchemaElement = JsonDocument.Parse(wrappedSchemaJson).RootElement;

        // Create new response format with the wrapped schema
        return ChatResponseFormat.ForJsonSchema(
            wrappedSchemaElement,
            schemaName,
            schemaDescription);
    }
#pragma warning restore CA1869
#pragma warning restore IL3050
#pragma warning restore IL2026

    /// <summary>
    /// Checks if the response format represents an array schema that needs wrapping.
    /// </summary>
    private static bool IsArraySchemaFormat(
        ChatResponseFormat responseFormat,
        out JsonElement schemaElement,
        out string? schemaName,
        out string? schemaDescription)
    {
        schemaElement = default;
        schemaName = null;
        schemaDescription = null;

        // Check if this is a JSON schema format
        if (responseFormat is not ChatResponseFormatJson jsonFormat)
        {
            return false;
        }

        // ChatResponseFormat.Schema contains the JSON schema as a JsonElement
        if (jsonFormat.Schema is null)
        {
            return false;
        }

        schemaElement = jsonFormat.Schema.Value;
        schemaName = jsonFormat.SchemaName;
        schemaDescription = jsonFormat.SchemaDescription;

        try
        {
            // Check if the root type is "array"
            if (schemaElement.TryGetProperty("type", out JsonElement typeElement))
            {
                string? rootType = typeElement.GetString();
                return rootType == "array";
            }

            return false;
        }
        catch
        {
            // If we can't parse the schema, don't attempt to wrap
            return false;
        }
    }
}
