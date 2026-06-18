// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Used to store a value in session state.
/// </summary>
[JsonConverter(typeof(AgentSessionStateBagValueJsonConverter))]
internal class AgentSessionStateBagValue
{
    private readonly object _lock = new();
    private DeserializedCache? _cache;
    private JsonElement _jsonValue;

    /// <summary>
    /// Initializes a new instance of the SessionStateValue class with the specified value.
    /// </summary>
    /// <param name="jsonValue">The serialized value to associate with the session state.</param>
    public AgentSessionStateBagValue(JsonElement jsonValue)
    {
        this.JsonValue = jsonValue;
    }

    /// <summary>
    /// Initializes a new instance of the SessionStateValue class with the specified value.
    /// </summary>
    /// <param name="deserializedValue">The value to associate with the session state. Can be any object, including null.</param>
    /// <param name="valueType">The type of the value.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for serializing the value.</param>
    public AgentSessionStateBagValue(object? deserializedValue, Type valueType, JsonSerializerOptions jsonSerializerOptions)
    {
        this._cache = new DeserializedCache(deserializedValue, valueType, jsonSerializerOptions);
    }

    /// <summary>
    /// Gets or sets the value associated with this instance.
    /// </summary>
    public JsonElement JsonValue
    {
        get
        {
            lock (this._lock)
            {
                // We are assuming here that JsonValue will only be read when the object is being serialized,
                // which means that we will only call SerializeToElement when serializing and therefore it's
                // OK to serialize on each read if the cache is set.
                if (this._cache is { } cache)
                {
                    this._jsonValue = JsonSerializer.SerializeToElement(cache.Value, cache.Options.GetTypeInfo(cache.ValueType));
                }

                return this._jsonValue;
            }
        }
        set
        {
            lock (this._lock)
            {
                this._jsonValue = value;
                this._cache = null;
            }
        }
    }

    /// <summary>
    /// Tries to read the deserialized value of this session state value.
    /// Returns false if the value could not be deserialized into the required type, or if the value is undefined.
    /// Returns true and sets the out parameter to null if the value is null.
    /// </summary>
    public bool TryReadDeserializedValue<T>(out T? value, JsonSerializerOptions? jsonSerializerOptions = null)
        where T : class
    {
        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;

        lock (this._lock)
        {
            switch (this._cache)
            {
                case DeserializedCache { Value: null, ValueType: Type cacheValueType } when cacheValueType == typeof(T):
                    value = null;
                    return true;
                case DeserializedCache { Value: T cacheValue, ValueType: Type cacheValueType } when cacheValueType == typeof(T):
                    value = cacheValue;
                    return true;
                case DeserializedCache { ValueType: Type cacheValueType } when cacheValueType != typeof(T):
                    value = null;
                    return false;
            }

            switch (this._jsonValue)
            {
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Undefined:
                    value = null;
                    return false;
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Null:
                    value = null;
                    return true;
                default:
                    T? result = this._jsonValue.Deserialize(jso.GetTypeInfo(typeof(T))) as T;
                    if (result is null)
                    {
                        value = null;
                        return false;
                    }

                    this._cache = new DeserializedCache(result, typeof(T), jso);

                    value = result;
                    return true;
            }
        }
    }

    /// <summary>
    /// Reads the deserialized value of this session state value, throwing an exception if the value could not be deserialized into the required type or is undefined.
    /// </summary>
    public T? ReadDeserializedValue<T>(JsonSerializerOptions? jsonSerializerOptions = null)
        where T : class
    {
        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;

        lock (this._lock)
        {
            switch (this._cache)
            {
                case DeserializedCache { Value: null, ValueType: Type cacheValueType } when cacheValueType == typeof(T):
                    return null;
                case DeserializedCache { Value: T cacheValue, ValueType: Type cacheValueType } when cacheValueType == typeof(T):
                    return cacheValue;
                case DeserializedCache { ValueType: Type cacheValueType } when cacheValueType != typeof(T):
                    throw new InvalidOperationException($"The type of the cached value is {cacheValueType.FullName}, but the requested type is {typeof(T).FullName}.");
            }

            switch (this._jsonValue)
            {
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Null || jsonElement.ValueKind == JsonValueKind.Undefined:
                    return null;
                default:
                    T? result = this._jsonValue.Deserialize(jso.GetTypeInfo(typeof(T))) as T;
                    if (result is null)
                    {
                        throw new InvalidOperationException($"Failed to deserialize session state value to type {typeof(T).FullName}.");
                    }

                    this._cache = new DeserializedCache(result, typeof(T), jso);
                    return result;
            }
        }
    }

    /// <summary>
    /// Sets the deserialized value of this session state value, updating the cache accordingly.
    /// This does not update the JsonValue directly; the JsonValue will be updated on the next read or when the object is serialized.
    /// </summary>
    public void SetDeserialized<T>(T? deserializedValue, Type valueType, JsonSerializerOptions jsonSerializerOptions)
    {
        lock (this._lock)
        {
            this._cache = new DeserializedCache(deserializedValue, valueType, jsonSerializerOptions);
        }
    }

    private readonly struct DeserializedCache
    {
        public DeserializedCache(object? value, Type valueType, JsonSerializerOptions options)
        {
            this.Value = value;
            this.ValueType = valueType;
            this.Options = options;
        }

        public object? Value { get; }

        public Type ValueType { get; }

        public JsonSerializerOptions Options { get; }
    }
}
