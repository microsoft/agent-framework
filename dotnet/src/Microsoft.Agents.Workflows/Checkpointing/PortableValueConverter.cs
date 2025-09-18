// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides special handling for <see cref="PortableValue"/> serialization and deserialization, enabling delayed deserialization
/// of the inner value. This is used to enable serialization/deserialization of objects whose type information is not available
/// at the time of initial deserialization, e.g. user-defined state types.
///
/// This operates in conjuction with <see cref="IDelayedDeserialization"/> and <see cref="PortableValue"/> to abstract
/// away the speicfics of a given serialization format in favor of <see cref="PortableValue.As{TValue}"/> and
/// <see cref="PortableValue.Is{TValue}"/>.
/// </summary>
/// <param name="marshaller"></param>
internal sealed class PortableValueConverter(JsonMarshaller marshaller) : JsonConverter<PortableValue>
{
    public override PortableValue? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition initial = reader.Position;

        JsonTypeInfo<PortableValue> baseTypeInfo = WorkflowsJsonUtilities.JsonContext.Default.PortableValue;
        PortableValue? maybeValue = JsonSerializer.Deserialize(ref reader, baseTypeInfo);

        if (maybeValue is null)
        {
            throw new JsonException($"Could not deserialize a PortableValue from JSON at position {initial}.");
        }
        else if (maybeValue.Value is JsonElement element)
        {
            // This happens when we do not have the type information available to deserialize the value directly.
            // We need to wrap it in a JsonWireSerializedValue so that we can deserialize it
            return new PortableValue(maybeValue.TypeId, new JsonWireSerializedValue(marshaller, element));
        }
        else if (maybeValue.TypeId.IsMatch(maybeValue.Value.GetType()))
        {
            return maybeValue;
        }

        throw new JsonException($"Deserialized PortableValue contains a value of type {maybeValue.Value.GetType()} which does not match the expected type {maybeValue.TypeId} at position {initial}.");
    }

    public override void Write(Utf8JsonWriter writer, PortableValue value, JsonSerializerOptions options)
    {
        PortableValue proxyValue;
        if (value.IsDelayedDeserialization && !value.IsDeserialized)
        {
            if (value.Value is JsonWireSerializedValue jsonWireValue)
            {
                proxyValue = new(value.TypeId, jsonWireValue.Data);
            }
            else
            {
                // Users should never see this unless they're trying to cross wire formats
                throw new InvalidOperationException("Cannot serialize a PortableValue that has not been deserialized. Please deserialize it with .As/AsType() or Is/IsType() methods first.");
            }
        }
        else
        {
            JsonElement element = marshaller.Marshal(value.Value, value.Value.GetType());
            proxyValue = new(value.TypeId, element);
        }

        JsonTypeInfo<PortableValue> baseTypeInfo = WorkflowsJsonUtilities.JsonContext.Default.PortableValue;
        JsonSerializer.Serialize(writer, proxyValue, baseTypeInfo);
    }
}
