// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a thread-safe key-value store for managing session-scoped state with support for type-safe access and JSON
/// serialization options.
/// </summary>
/// <remarks>
/// SessionState enables storing and retrieving objects associated with a session using string keys.
/// Values can be accessed in a type-safe manner and are serialized or deserialized using configurable JSON serializer
/// options. This class is designed for concurrent access and is safe to use across multiple threads.
/// </remarks>
[JsonConverter(typeof(AgentSessionStateBagJsonConverter))]
public class AgentSessionStateBag
{
    private readonly ConcurrentDictionary<string, AgentSessionStateBagValue> _state;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSessionStateBag"/> class.
    /// </summary>
    public AgentSessionStateBag()
    {
        this._state = new ConcurrentDictionary<string, AgentSessionStateBagValue>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSessionStateBag"/> class.
    /// </summary>
    /// <param name="state">The initial state dictionary.</param>
    internal AgentSessionStateBag(ConcurrentDictionary<string, AgentSessionStateBagValue>? state)
    {
        this._state = state ?? new ConcurrentDictionary<string, AgentSessionStateBagValue>();
    }

    /// <summary>
    /// Gets the number of key-value pairs contained in the session state.
    /// </summary>
    public int Count => this._state.Count;

    /// <summary>
    /// Tries to get a value from the session state.
    /// </summary>
    /// <typeparam name="T">The type of the value to retrieve.</typeparam>
    /// <param name="key">The key from which to retrieve the value.</param>
    /// <param name="value">The value if found and convertable to the required type; otherwise, null.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for serializing/deserialing the value.</param>
    /// <returns><see langword="true"/> if the value was successfully retrieved, <see langword="false"/> otherwise.</returns>
    public bool TryGetValue<T>(string key, out T? value, JsonSerializerOptions? jsonSerializerOptions = null)
        where T : class
    {
        _ = Throw.IfNullOrWhitespace(key);
        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;

        if (this._state.TryGetValue(key, out var stateValue))
        {
            if (stateValue.DeserializedValue is T cachedValue)
            {
                value = cachedValue;
                return true;
            }

            switch (stateValue.JsonValue)
            {
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Undefined:
                    value = null;
                    return false;
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Null:
                    value = null;
                    return true;
                default:
                    T? result = stateValue.JsonValue.Deserialize(jso.GetTypeInfo(typeof(T))) as T;
                    if (result is null)
                    {
                        value = null;
                        return false;
                    }

                    stateValue.DeserializedValue = result;
                    stateValue.ValueType = typeof(T);
                    stateValue.JsonSerializerOptions = jso;

                    value = result;
                    return true;
            }
        }
        value = null;
        return false;
    }

    /// <summary>
    /// Gets a value from the session state.
    /// </summary>
    /// <typeparam name="T">The type of value to get.</typeparam>
    /// <param name="key">The key from which to retrieve the value.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for serializing/deserialing the value.</param>
    /// <returns>The retrieved value or null if not found.</returns>
    /// <exception cref="InvalidOperationException">The value could not be deserialized into the required type.</exception>
    public T? GetValue<T>(string key, JsonSerializerOptions? jsonSerializerOptions = null)
        where T : class
    {
        _ = Throw.IfNullOrWhitespace(key);
        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;

        if (this._state.TryGetValue(key, out var stateValue))
        {
            if (stateValue.DeserializedValue is T cachedValue)
            {
                return cachedValue;
            }

            switch (stateValue.JsonValue)
            {
                case JsonElement jsonElement when jsonElement.ValueKind == JsonValueKind.Null || jsonElement.ValueKind == JsonValueKind.Undefined:
                    return null;
                default:
                    T? result = stateValue.JsonValue.Deserialize(jso.GetTypeInfo(typeof(T))) as T;
                    if (result is null)
                    {
                        throw new InvalidOperationException($"Failed to deserialize session state value to type {typeof(T).FullName}.");
                    }
                    stateValue.IsDeserialized = true;
                    stateValue.DeserializedValue = result;
                    stateValue.ValueType = typeof(T);
                    stateValue.JsonSerializerOptions = jso;
                    return result;
            }
        }

        return null;
    }

    /// <summary>
    /// Sets a value in the session state.
    /// </summary>
    /// <typeparam name="T">The type of the value to set.</typeparam>
    /// <param name="key">The key to store the value under.</param>
    /// <param name="value">The value to set.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for serializing the value.</param>
    public void SetValue<T>(string key, T? value, JsonSerializerOptions? jsonSerializerOptions = null)
        where T : class
    {
        _ = Throw.IfNullOrWhitespace(key);
        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;

        var stateValue = this._state.GetOrAdd(key, _ =>
            new AgentSessionStateBagValue(value, typeof(T), jso));

        stateValue.IsDeserialized = true;
        stateValue.DeserializedValue = value;
        stateValue.ValueType = typeof(T);
        stateValue.JsonSerializerOptions = jso;
    }

    /// <summary>
    /// Tries to remove a value from the session state.
    /// </summary>
    /// <param name="key">The key of the value to remove.</param>
    /// <returns><see langword="true"/> if the value was successfully removed; otherwise, <see langword="false"/>.</returns>
    public bool TryRemoveValue(string key)
        => this._state.TryRemove(Throw.IfNullOrWhitespace(key), out _);

    /// <summary>
    /// Serializes all session state values to a JSON object.
    /// </summary>
    /// <returns>A <see cref="JsonElement"/> representing the serialized session state.</returns>
    /// <exception cref="InvalidOperationException">Thrown when a session state value is not properly initialized.</exception>
    public JsonElement Serialize()
    {
        return JsonSerializer.SerializeToElement(this._state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ConcurrentDictionary<string, AgentSessionStateBagValue>)));
    }

    /// <summary>
    /// Deserializes a JSON object into an <see cref="AgentSessionStateBag"/> instance.
    /// </summary>
    /// <param name="jsonElement">The element to deserialize.</param>
    /// <returns>The deserialized <see cref="AgentSessionStateBag"/>.</returns>
    public static AgentSessionStateBag Deserialize(JsonElement jsonElement)
    {
        if (jsonElement.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return new AgentSessionStateBag();
        }

        return new AgentSessionStateBag(
            jsonElement.Deserialize(AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ConcurrentDictionary<string, AgentSessionStateBagValue>))) as ConcurrentDictionary<string, AgentSessionStateBagValue>
            ?? new ConcurrentDictionary<string, AgentSessionStateBagValue>());
    }
}
