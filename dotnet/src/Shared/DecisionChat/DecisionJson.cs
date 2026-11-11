// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// JSON value helpers for converting chat messages and tool arguments into decision state and back.
/// </summary>
internal static class DecisionJson
{
    private static readonly JsonElement s_true = Parse("true");
    private static readonly JsonElement s_false = Parse("false");
    private static readonly JsonElement s_null = Parse("null");

    /// <summary>
    /// Converts one tool argument into a JSON node. Chat clients pass arguments as <see cref="JsonElement"/> values;
    /// callers that invoke the function directly may pass .NET objects instead, which are serialized with
    /// <see cref="AIJsonUtilities.DefaultOptions"/>.
    /// </summary>
    public static JsonNode? ToNode(object? value) =>
        value switch
        {
            null => null,
            JsonNode node => node.DeepClone(),
            JsonElement element => element.ValueKind switch
            {
                JsonValueKind.Object => JsonObject.Create(element),
                JsonValueKind.Array => JsonArray.Create(element),
                JsonValueKind.Null or JsonValueKind.Undefined => null,
                _ => JsonValue.Create(element),
            },
            _ => JsonSerializer.SerializeToNode(value, AIJsonUtilities.DefaultOptions.GetTypeInfo(value.GetType())),
        };

    /// <summary>
    /// Converts a value from a chat message, such as a function argument or result, into a JSON node. A value that
    /// cannot be serialized, for example a type without metadata under native AOT, becomes its text.
    /// </summary>
    public static JsonNode? ToNodeOrText(object? value)
    {
        try
        {
            return ToNode(value);
        }
        catch (Exception ex) when (ex is NotSupportedException or InvalidOperationException or JsonException or ArgumentException)
        {
            // Chat history is informational for the decision model, so an unserializable value is described rather
            // than failing the whole request.
            return JsonValue.Create(value?.ToString());
        }
    }

    /// <summary>Converts a value from a chat message into a detached <see cref="JsonElement"/>, like <see cref="ToNodeOrText"/>.</summary>
    public static JsonElement ToElement(object? value) =>
        value switch
        {
            JsonElement element => element.ValueKind == JsonValueKind.Undefined ? s_null : element.Clone(),
            null => s_null,
            _ => Parse(ToNodeOrText(value)?.ToJsonString() ?? "null"),
        };

    /// <summary>Gets the JSON <see langword="true"/> or <see langword="false"/> value.</summary>
    public static JsonElement CreateBoolean(bool value) => value ? s_true : s_false;

    /// <summary>Writes values into a new JSON array.</summary>
    public static JsonElement CreateArray(IEnumerable<JsonElement> values)
    {
        var buffer = new ArrayBufferWriter<byte>();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartArray();
            foreach (JsonElement value in values)
            {
                value.WriteTo(writer);
            }

            writer.WriteEndArray();
        }

        using JsonDocument document = JsonDocument.Parse(buffer.WrittenMemory);
        return document.RootElement.Clone();
    }

    /// <summary>Parses JSON text into a detached <see cref="JsonElement"/>.</summary>
    public static JsonElement Parse(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
