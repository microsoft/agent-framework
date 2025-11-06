// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents a reference to a conversation, which can be either a conversation ID (string) or a conversation object.
/// </summary>
[JsonConverter(typeof(ConversationReferenceJsonConverter))]
internal sealed class ConversationReference
{
    /// <summary>
    /// The conversation ID.
    /// </summary>
    [JsonPropertyName("id")]
    public string? Id { get; init; }

    /// <summary>
    /// The conversation metadata (optional, only when passing a conversation object).
    /// </summary>
    [JsonPropertyName("metadata")]
    public Dictionary<string, string>? Metadata { get; init; }

    /// <summary>
    /// Creates a conversation reference from a conversation ID.
    /// </summary>
    public static ConversationReference FromId(string id) => new() { Id = id };

    /// <summary>
    /// Creates a conversation reference from a conversation object.
    /// </summary>
    public static ConversationReference FromObject(string id, Dictionary<string, string>? metadata = null) =>
        new() { Id = id, Metadata = metadata };
}

/// <summary>
/// JSON converter for ConversationReference that handles both string (conversation ID) and object representations.
/// </summary>
internal sealed class ConversationReferenceJsonConverter : JsonConverter<ConversationReference>
{
    /// <inheritdoc/>
    public override ConversationReference? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String)
        {
            // Handle string format: just the conversation ID
            var id = reader.GetString();
            return id is null ? null : ConversationReference.FromId(id);
        }
        else if (reader.TokenType == JsonTokenType.StartObject)
        {
            // Handle object format: { "id": "...", "metadata": {...} }
            using var doc = JsonDocument.ParseValue(ref reader);
            var root = doc.RootElement;

            var id = root.TryGetProperty("id", out var idProp) ? idProp.GetString() : null;
            Dictionary<string, string>? metadata = null;

            if (root.TryGetProperty("metadata", out var metadataProp) && metadataProp.ValueKind == JsonValueKind.Object)
            {
                metadata = JsonSerializer.Deserialize(metadataProp.GetRawText(), OpenAIHostingJsonContext.Default.DictionaryStringString);
            }

            return id is null ? null : ConversationReference.FromObject(id, metadata);
        }
        else if (reader.TokenType == JsonTokenType.Null)
        {
            return null;
        }

        throw new JsonException($"Unexpected token type for ConversationReference: {reader.TokenType}");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ConversationReference value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        // If only ID is present and no metadata, serialize as a simple string
        if (value.Metadata is null || value.Metadata.Count == 0)
        {
            writer.WriteStringValue(value.Id);
        }
        else
        {
            // Otherwise, serialize as an object
            writer.WriteStartObject();
            writer.WriteString("id", value.Id);
            if (value.Metadata is not null)
            {
                writer.WritePropertyName("metadata");
                JsonSerializer.Serialize(writer, value.Metadata, OpenAIHostingJsonContext.Default.DictionaryStringString);
            }
            writer.WriteEndObject();
        }
    }
}
