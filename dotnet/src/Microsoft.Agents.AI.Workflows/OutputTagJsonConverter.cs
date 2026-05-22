// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// JSON converter for <see cref="OutputTag"/> that round-trips the underlying
/// <see cref="OutputTag.Value"/> as a bare JSON string.
/// </summary>
internal sealed class OutputTagJsonConverter : JsonConverter<OutputTag>
{
    public override OutputTag Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        string? value = reader.GetString();
        if (string.IsNullOrEmpty(value))
        {
            return default;
        }

        // Reuse the well-known singleton where possible so callers can do reference
        // comparisons on the common case without paying the extra allocation cost.
        if (string.Equals(value, OutputTag.Intermediate.Value, StringComparison.Ordinal))
        {
            return OutputTag.Intermediate;
        }

        return new OutputTag(value!);
    }

    public override void Write(Utf8JsonWriter writer, OutputTag value, JsonSerializerOptions options)
    {
        if (value.Value is null)
        {
            writer.WriteNullValue();
            return;
        }

        writer.WriteStringValue(value.Value);
    }
}
