// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the result of a list keys operation containing the found keys and optional continuation token.
/// </summary>
/// <param name="keys">The collection of keys found in the actor's state.</param>
/// <param name="continuationToken">Optional token for pagination to retrieve additional keys.</param>
public sealed class ListKeysResult(IReadOnlyCollection<string> keys, string? continuationToken) : ActorReadResult
{
    /// <summary>
    /// Gets the collection of keys found in the actor's state.
    /// </summary>
    [JsonPropertyName("keys")]
    public IReadOnlyCollection<string> Keys { get; } = keys;

    /// <summary>
    /// Gets the continuation token for pagination.
    /// </summary>
    [JsonPropertyName("continuationToken")]
    public string? ContinuationToken { get; } = continuationToken;

    /// <summary>
    /// Gets the type of the read result operation.
    /// </summary>
    public override ActorReadResultType Type => ActorReadResultType.ListKeys;
}
