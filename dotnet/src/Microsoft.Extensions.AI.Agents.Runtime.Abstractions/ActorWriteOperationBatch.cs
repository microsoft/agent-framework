// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a batch of write operations to be performed atomically on an actor.
/// </summary>
/// <param name="eTag">The ETag for optimistic concurrency control.</param>
/// <param name="operations">The collection of write operations to perform.</param>
public class ActorWriteOperationBatch(string eTag, IReadOnlyCollection<ActorWriteOperation> operations)
{
    /// <summary>
    /// Gets the collection of write operations to perform.
    /// </summary>
    [JsonPropertyName("operations")]
    public IReadOnlyCollection<ActorWriteOperation> Operations { get; } = operations;

    /// <summary>
    /// Gets the ETag for optimistic concurrency control.
    /// </summary>
    [JsonPropertyName("etag")]
    public string ETag { get; } = eTag;
}
