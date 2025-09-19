// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides support for JSON serialization and deserialization using a specified JsonTypeInfo.
/// </summary>
/// <typeparam name="T"></typeparam>
internal abstract class JsonConverterBase<T> : JsonConverter<T>
{
    protected abstract JsonTypeInfo<T> TypeInfo { get; }

    public override T? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition position = reader.Position;
        return
            JsonSerializer.Deserialize(ref reader, this.TypeInfo) ??
            throw new JsonException($"Could not deserialize a {typeof(T).Name} from JSON at position {position}");
    }

    public override void Write(Utf8JsonWriter writer, T value, JsonSerializerOptions options) =>
        JsonSerializer.Serialize(writer, value, this.TypeInfo);
}
