// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a request to read a value from the actor's state by its key.
/// </summary>
/// <param name="key">The key corresponding to the value to read from the actor's state.</param>
public sealed class GetValueOperation(string key) : ActorStateReadOperation
{
    /// <summary>
    /// Gets the key corresponding to the value to read from the actor's state.
    /// </summary>
    [JsonPropertyName("key")]
    public string Key { get; } = key;

    /// <summary>
    /// Gets the type of the read operation.
    /// </summary>
    public override ActorReadOperationType Type => ActorReadOperationType.GetValue;
}
