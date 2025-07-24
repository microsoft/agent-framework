// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a batch of read operations to be performed on an actor.
/// </summary>
/// <param name="operations">The collection of read operations to perform.</param>
public sealed class ActorReadOperationBatch(IReadOnlyList<ActorReadOperation> operations)
{
    /// <summary>
    /// Gets the collection of read operations to perform.
    /// </summary>
    [JsonPropertyName("operations")]
    public IReadOnlyList<ActorReadOperation> Operations { get; } = operations;
}
