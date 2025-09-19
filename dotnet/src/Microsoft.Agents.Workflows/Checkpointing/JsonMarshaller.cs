// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class JsonMarshaller : IWireMarshaller<JsonElement>
{
    private readonly JsonSerializerOptions _internalOptions;
    private readonly JsonSerializerOptions? _externalOptions;

    public JsonMarshaller(JsonSerializerOptions? serializerOptions = null)
    {
        this._internalOptions = new JsonSerializerOptions(WorkflowsJsonUtilities.DefaultOptions);
        this._internalOptions.Converters.Add(new PortableValueConverter(this));
        this._internalOptions.Converters.Add(new ExecutorIdentityConverter());
        this._internalOptions.Converters.Add(new ScopeKeyConverter());
        this._internalOptions.Converters.Add(new EdgeIdConverter());

        this._externalOptions = serializerOptions;
    }

    private JsonTypeInfo LookupTypeInfo(Type type)
    {
        if (!this._internalOptions.TryGetTypeInfo(type, out JsonTypeInfo? typeInfo))
        {
            if (this._externalOptions is null ||
                !this._externalOptions.TryGetTypeInfo(type, out typeInfo))
            {
                throw new InvalidOperationException($"No JSON type info is available for type '{type}'.");
            }
        }

        return typeInfo;
    }

    public JsonElement Marshal(object value, Type type)
        => JsonSerializer.SerializeToElement(value, this.LookupTypeInfo(type));

    public JsonElement Marshal<TValue>(TValue value)
        => JsonSerializer.SerializeToElement(value, this.LookupTypeInfo(typeof(TValue)));

    public TValue Marshal<TValue>(JsonElement data)
    {
        object value = data.Deserialize(this.LookupTypeInfo(typeof(TValue))) ??
            throw new InvalidOperationException($"Could not deserialize the value as the expected type {typeof(TValue)}.");

        if (value is TValue typedValue)
        {
            return typedValue;
        }

        throw new InvalidOperationException($"Deserialized value is not of the expected type {typeof(TValue)}.");
    }

    public object Marshal(Type targetType, JsonElement data)
    {
        object value = data.Deserialize(this.LookupTypeInfo(targetType)) ??
            throw new InvalidOperationException($"Could not deserialize the value as the expected type {targetType}.");

        if (targetType.IsInstanceOfType(value))
        {
            return value;
        }

        throw new InvalidOperationException($"Deserialized value is not of the expected type {targetType}.");
    }
}
