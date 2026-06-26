// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Reads a JSON value as a string, returning <see langword="null"/> for any non-string token instead of
/// throwing. Used for the optional <c>safety_identifier</c> / <c>user</c> identity fields so a malformed
/// (e.g. numeric) value is ignored, matching Python's <c>parse_responses_identity</c> which yields no identity
/// for non-string values rather than rejecting the request.
/// </summary>
internal sealed class LenientStringConverter : JsonConverter<string?>
{
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String)
        {
            return reader.GetString();
        }

        if (reader.TokenType is JsonTokenType.StartObject or JsonTokenType.StartArray)
        {
            reader.Skip();
        }

        return null;
    }

    public override void Write(Utf8JsonWriter writer, string? value, JsonSerializerOptions options) =>
        writer.WriteStringValue(value);
}
