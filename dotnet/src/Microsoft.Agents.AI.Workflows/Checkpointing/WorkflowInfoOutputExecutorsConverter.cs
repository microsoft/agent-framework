// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// JSON converter for <see cref="WorkflowInfo.OutputExecutorIds"/> that supports both the new
/// map shape (<c>{ "id": ["intermediate"] }</c>) and the legacy array shape
/// (<c>["id1", "id2"]</c>). Legacy-shaped payloads are read as if every id had been registered
/// as a regular (untagged) output source; output is always written in the new map shape.
/// </summary>
internal sealed class WorkflowInfoOutputExecutorsConverter : JsonConverter<Dictionary<string, HashSet<OutputTag>>>
{
    public override Dictionary<string, HashSet<OutputTag>> Read(
        ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        Dictionary<string, HashSet<OutputTag>> result = new(StringComparer.Ordinal);

        if (reader.TokenType == JsonTokenType.Null)
        {
            return result;
        }

        if (reader.TokenType == JsonTokenType.StartArray)
        {
            // Legacy shape: a flat array of executor ids. Treat each as a registered
            // (untagged) output executor.
            while (reader.Read())
            {
                if (reader.TokenType == JsonTokenType.EndArray)
                {
                    return result;
                }

                if (reader.TokenType != JsonTokenType.String)
                {
                    throw new JsonException($"Expected a string in legacy outputExecutorIds array, got {reader.TokenType}.");
                }

                string id = reader.GetString()!;
                result[id] = [];
            }

            throw new JsonException("Unexpected end of legacy outputExecutorIds array.");
        }

        if (reader.TokenType != JsonTokenType.StartObject)
        {
            throw new JsonException($"Expected object or array for outputExecutorIds, got {reader.TokenType}.");
        }

        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndObject)
            {
                return result;
            }

            if (reader.TokenType != JsonTokenType.PropertyName)
            {
                throw new JsonException($"Expected property name in outputExecutorIds object, got {reader.TokenType}.");
            }

            string id = reader.GetString()!;
            reader.Read();

            HashSet<OutputTag> tags = [];
            if (reader.TokenType == JsonTokenType.StartArray)
            {
                while (reader.Read() && reader.TokenType != JsonTokenType.EndArray)
                {
                    if (reader.TokenType != JsonTokenType.String)
                    {
                        throw new JsonException($"Expected a string tag, got {reader.TokenType}.");
                    }

                    tags.Add(ReadTag(reader.GetString()!));
                }
            }
            else
            {
                throw new JsonException($"Expected array of tags for outputExecutorIds[{id}], got {reader.TokenType}.");
            }

            result[id] = tags;
        }

        throw new JsonException("Unexpected end of outputExecutorIds object.");
    }

    private static OutputTag ReadTag(string value)
    {
        if (string.Equals(value, OutputTag.Intermediate.Value, StringComparison.Ordinal))
        {
            return OutputTag.Intermediate;
        }
        return new OutputTag(value);
    }

    public override void Write(
        Utf8JsonWriter writer,
        Dictionary<string, HashSet<OutputTag>> value,
        JsonSerializerOptions options)
    {
        writer.WriteStartObject();
        foreach (KeyValuePair<string, HashSet<OutputTag>> kvp in value)
        {
            writer.WritePropertyName(kvp.Key);
            writer.WriteStartArray();
            foreach (OutputTag tag in kvp.Value)
            {
                writer.WriteStringValue(tag.Value);
            }
            writer.WriteEndArray();
        }
        writer.WriteEndObject();
    }
}
