// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents an operation to remove a key from an actor's state.
/// </summary>
/// <param name="Key">The key to remove from the actor's state.</param>
public sealed class RemoveKeyOperation(string Key) : ActorStateWriteOperation
{
    /// <summary>
    /// Gets the key for the state operation.
    /// </summary>
    [JsonPropertyName("key")]
    public string Key { get; } = Key;

    /// <summary>
    /// Gets the type of the write operation.
    /// </summary>
    public override ActorWriteOperationType Type => ActorWriteOperationType.RemoveKey;
}
