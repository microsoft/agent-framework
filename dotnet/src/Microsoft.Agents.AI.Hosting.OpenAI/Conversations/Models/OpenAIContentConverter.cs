// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// JSON converter for lists of AIContent that produces OpenAI-compatible format.
/// </summary>
[SuppressMessage("CodeQuality", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via reflection by JSON serialization.")]
internal sealed class OpenAIContentListConverter : JsonConverter<IList<AIContent>>
{
    private static readonly OpenAIContentConverter s_itemConverter = new();

    public override IList<AIContent>? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.StartArray)
        {
            throw new JsonException($"Expected StartArray token, got {reader.TokenType}");
        }

        var list = new List<AIContent>();
        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndArray)
            {
                return list;
            }

            var item = s_itemConverter.Read(ref reader, typeof(AIContent), options);
            if (item is not null)
            {
                list.Add(item);
            }
        }

        throw new JsonException("Unexpected end of JSON");
    }

    public override void Write(Utf8JsonWriter writer, IList<AIContent> value, JsonSerializerOptions options)
    {
        writer.WriteStartArray();
        foreach (var item in value)
        {
            s_itemConverter.Write(writer, item, options);
        }
        writer.WriteEndArray();
    }
}

/// <summary>
/// JSON converter for AIContent that produces OpenAI-compatible format.
/// Converts TextContent to {"type": "input_text", "text": "..."} format.
/// </summary>
internal sealed class OpenAIContentConverter : JsonConverter<AIContent>
{
    public override AIContent? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var root = doc.RootElement;

        string? contentType = null;

        // Check if this is OpenAI format with a "type" property
        if (root.TryGetProperty("type", out var typeProperty))
        {
            contentType = typeProperty.GetString();

            // Handle OpenAI text format: {"type": "text", "text": "..."}
            // Also support input_text/output_text for backwards compatibility
            if ((contentType == "text" || contentType == "input_text" || contentType == "output_text") &&
                root.TryGetProperty("text", out var textProperty))
            {
                var text = textProperty.GetString();
                if (!string.IsNullOrEmpty(text))
                {
                    return new TextContent(text);
                }
            }
        }

        // Fall back to standard AIContent deserialization using our context
        // This works in both AOT and non-AOT scenarios
        return JsonSerializer.Deserialize(root.GetRawText(), ConversationsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent))) as AIContent;
    }

    public override void Write(Utf8JsonWriter writer, AIContent value, JsonSerializerOptions options)
    {
        writer.WriteStartObject();

        // Convert TextContent to OpenAI format
        if (value is TextContent textContent)
        {
            // Use "text" as per OpenAI Conversations API standard
            writer.WriteString("type", "text");
            writer.WriteString("text", textContent.Text);

            // Include annotations if present
            if (textContent.AdditionalProperties?.Count > 0)
            {
                foreach (var kvp in textContent.AdditionalProperties)
                {
                    var propertyName = options.PropertyNamingPolicy?.ConvertName(kvp.Key) ?? kvp.Key;
                    writer.WritePropertyName(propertyName);
                    // Use ConversationsJsonContext for AOT-safe serialization
                    JsonSerializer.Serialize(writer, kvp.Value, ConversationsJsonContext.Default.Object);
                }
            }
        }
        else
        {
            // For other content types, serialize using our context
            // This works in both AOT and non-AOT scenarios
            var element = JsonSerializer.SerializeToElement(value, ConversationsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent)));
            foreach (var property in element.EnumerateObject())
            {
                property.WriteTo(writer);
            }
        }

        writer.WriteEndObject();
    }
}
