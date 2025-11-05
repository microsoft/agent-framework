// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Models;

/// <summary>
/// Specifies the sort order for list operations.
/// </summary>
[JsonConverter(typeof(SortOrderJsonConverter))]
internal enum SortOrder
{
    /// <summary>
    /// Sort in ascending order (oldest to newest).
    /// </summary>
    Ascending,

    /// <summary>
    /// Sort in descending order (newest to oldest).
    /// </summary>
    Descending
}

/// <summary>
/// Custom JSON converter for SortOrder enum to serialize as "asc" and "desc".
/// </summary>
internal sealed class SortOrderJsonConverter : JsonConverter<SortOrder>
{
    /// <inheritdoc/>
    public override SortOrder Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var value = reader.GetString();
        return value switch
        {
            string s when s.Equals("asc", StringComparison.OrdinalIgnoreCase) => SortOrder.Ascending,
            string s when s.Equals("desc", StringComparison.OrdinalIgnoreCase) => SortOrder.Descending,
            null => throw new JsonException("SortOrder value cannot be null"),
            _ => throw new JsonException($"Invalid SortOrder value: {value}")
        };
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, SortOrder value, JsonSerializerOptions options)
    {
        var stringValue = value switch
        {
            SortOrder.Ascending => "asc",
            SortOrder.Descending => "desc",
            _ => throw new JsonException($"Invalid SortOrder value: {value}")
        };
        writer.WriteStringValue(stringValue);
    }
}
