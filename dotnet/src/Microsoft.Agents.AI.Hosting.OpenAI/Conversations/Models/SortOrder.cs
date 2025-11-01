// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

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
        return value?.ToUpperInvariant() switch
        {
            "ASC" => SortOrder.Ascending,
            "DESC" => SortOrder.Descending,
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
