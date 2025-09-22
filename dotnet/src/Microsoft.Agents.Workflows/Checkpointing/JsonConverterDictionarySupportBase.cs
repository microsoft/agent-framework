// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <typeparamref name="T"/> values as dictionary keys when serializing and deserializing JSON.
/// It chains to the provided <see cref="JsonTypeInfo{T}"/> for serialization and deserialization when not used as a property
/// name.
/// </summary>
/// <typeparam name="T"></typeparam>
internal abstract class JsonConverterDictionarySupportBase<T> : JsonConverterBase<T>
{
    protected abstract string Stringify([DisallowNull] T value);
    protected abstract T Parse(string propertyName);

    public override T ReadAsPropertyName(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition position = reader.Position;

        string? propertyName = reader.GetString() ??
            throw new JsonException($"Got null trying to read property name at position {position}");

        return this.Parse(propertyName);
    }

    public override void WriteAsPropertyName(Utf8JsonWriter writer, [DisallowNull] T value, JsonSerializerOptions options)
    {
        string propertyName = this.Stringify(value);
        writer.WritePropertyName(propertyName);
    }
}
