// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary.

using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal utilities for working with structured output JSON schemas.
/// </summary>
internal static class StructuredOutputSchemaUtilities
{
    private const string DataPropertyName = "data";

    /// <summary>
    /// Ensures the given response format has an object schema at the root, wrapping non-object schemas if necessary.
    /// </summary>
    /// <param name="responseFormat">The response format to check.</param>
    /// <returns>A tuple containing the (possibly wrapped) response format and whether wrapping occurred.</returns>
    /// <exception cref="InvalidOperationException">The response format does not have a valid JSON schema.</exception>
    internal static (ChatResponseFormatJson ResponseFormat, bool IsWrappedInObject) WrapNonObjectSchema(ChatResponseFormatJson responseFormat)
    {
        if (responseFormat.Schema is null)
        {
            throw new InvalidOperationException("The response format must have a valid JSON schema.");
        }

        var schema = responseFormat.Schema.Value;
        bool isWrappedInObject = false;

        if (!SchemaRepresentsObject(responseFormat.Schema))
        {
            // For non-object-representing schemas, we wrap them in an object schema, because all
            // the real LLM providers today require an object schema as the root. This is currently
            // true even for providers that support native structured output.
            isWrappedInObject = true;
            schema = JsonSerializer.SerializeToElement(new JsonObject
            {
                { "$schema", "https://json-schema.org/draft/2020-12/schema" },
                { "type", "object" },
                { "properties", new JsonObject { { DataPropertyName, JsonElementToJsonNode(schema) } } },
                { "additionalProperties", false },
                { "required", new JsonArray(DataPropertyName) },
            }, AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(JsonObject)));

            responseFormat = ChatResponseFormat.ForJsonSchema(schema, responseFormat.SchemaName, responseFormat.SchemaDescription);
        }

        return (responseFormat, isWrappedInObject);
    }

    /// <summary>
    /// Unwraps the <c>"data"</c> property from a JSON object that was previously wrapped by <see cref="WrapNonObjectSchema"/>.
    /// </summary>
    /// <param name="json">The JSON string to unwrap.</param>
    /// <returns>The raw JSON text of the <c>"data"</c> property, or the original JSON if no wrapping is detected.</returns>
    internal static string UnwrapResponseData(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind == JsonValueKind.Object &&
            document.RootElement.TryGetProperty(DataPropertyName, out JsonElement dataElement))
        {
            return dataElement.GetRawText();
        }

        // If root is not an object or "data" property is not found, return the original JSON as a fallback
        return json;
    }

    private static bool SchemaRepresentsObject(JsonElement? schema)
    {
        if (schema is not { } schemaElement)
        {
            return false;
        }

        if (schemaElement.ValueKind is JsonValueKind.Object)
        {
            foreach (var property in schemaElement.EnumerateObject())
            {
                if (property.NameEquals("type"u8))
                {
                    return property.Value.ValueKind == JsonValueKind.String
                        && property.Value.ValueEquals("object"u8);
                }
            }
        }

        return false;
    }

    private static JsonNode? JsonElementToJsonNode(JsonElement element) =>
        element.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.Array => JsonArray.Create(element),
            JsonValueKind.Object => JsonObject.Create(element),
            _ => JsonValue.Create(element)
        };
}
