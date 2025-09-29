// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Represents an operation to list keys from an actor's state, with optional pagination support.
/// </summary>
/// <param name="continuationToken">Optional token for pagination to continue listing from a previous operation.</param>
/// <param name="keyPrefix">Optional prefix to filter keys. Only keys starting with this prefix will be returned.</param>
public sealed class ListKeysOperation(string? continuationToken, string? keyPrefix = null) : ActorStateReadOperation
{
    /// <summary>
    /// Gets the continuation token for pagination.
    /// </summary>
    [JsonPropertyName("continuationToken")]
    public string? ContinuationToken { get; } = continuationToken;

    /// <summary>
    /// Gets the key prefix for filtering. Only keys starting with this prefix will be returned.
    /// </summary>
    [JsonPropertyName("keyPrefix")]
    public string? KeyPrefix { get; } = keyPrefix;

    /// <summary>
    /// Gets the type of the read operation.
    /// </summary>
    public override ActorReadOperationType Type => ActorReadOperationType.ListKeys;
}
