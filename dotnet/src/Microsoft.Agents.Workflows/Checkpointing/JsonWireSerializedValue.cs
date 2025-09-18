// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Represents a value serialized to the JSON format (<see cref="JsonMarshaller"/>).
/// When type information is not available during deserialization, this will wrap a clone of the
/// <see cref="JsonElement"/> to be deserialized later.
/// </summary>
/// <param name="serializer"></param>
/// <param name="data"></param>
/// <seealso cref="PortableValue"/>
internal sealed class JsonWireSerializedValue(JsonMarshaller serializer, JsonElement data) : IDelayedDeserialization
{
    internal JsonElement Data { get; } = data.Clone();

    public TValue Deserialize<TValue>() => serializer.Marshal<TValue>(data);

    public object? Deserialize(Type targetType) => serializer.Marshal(targetType, data);

    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is JsonWireSerializedValue otherValue)
        {
            return JsonElement.DeepEquals(this.Data, otherValue.Data);
        }
        else if (obj is JsonElement element)
        {
            return this.Data.Equals(element);
        }
        else if (obj is not IDelayedDeserialization)
        {
            // Assume this has the target type of deserialization; serialize it using the explicit type
            // and compare. Of course, this also means that if this is a supertype, it could encounter
            // truncation.
            try
            {
                JsonElement otherElement = serializer.Marshal(obj, obj.GetType());

                return JsonElement.DeepEquals(this.Data, otherElement);
            }
            catch
            {
                return false;
            }
        }

        return false;
    }

    public override int GetHashCode()
    {
        return this.Data.GetHashCode();
    }
}
