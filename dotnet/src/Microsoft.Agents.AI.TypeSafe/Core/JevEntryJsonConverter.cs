// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Reads and writes a <see cref="JevEntry"/> as the JSON value it holds.
/// </summary>
internal sealed class JevEntryJsonConverter : JsonConverter<JevEntry>
{
    // A JSON null is a valid entry (an undescribed criterion), so the converter reads it instead of the serializer.
    public override bool HandleNull => true;

    public override JevEntry Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        JsonElement value = JsonElement.ParseValue(ref reader);
        if (value.ValueKind is JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False)
        {
            throw new JsonException("A Jev entry must be text, a JSON object or array, or null.");
        }

        return new JevEntry(value);
    }

    public override void Write(Utf8JsonWriter writer, JevEntry value, JsonSerializerOptions options)
    {
        if (value.Json is { } json)
        {
            json.WriteTo(writer);
        }
        else
        {
            writer.WriteNullValue();
        }
    }
}
