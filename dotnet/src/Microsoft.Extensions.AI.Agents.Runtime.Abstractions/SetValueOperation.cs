// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents an operation to set a key-value pair in an actor's state.
/// </summary>
/// <param name="Key">The key to set in the actor's state.</param>
/// <param name="Value">The value to associate with the key.</param>
public sealed class SetValueOperation(string Key, JsonElement Value) : ActorStateWriteOperation
{
    /// <summary>
    /// Gets the key for the state operation.
    /// </summary>
    [JsonPropertyName("key")]
    public string Key { get; } = Key;

    /// <summary>
    /// Gets the value for the state operation.
    /// </summary>
    [JsonPropertyName("value")]
    public JsonElement Value { get; } = Value;

    /// <summary>
    /// Gets the type of the write operation.
    /// </summary>
    public override ActorWriteOperationType Type => ActorWriteOperationType.SetValue;
}
