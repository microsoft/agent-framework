// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// The response of a read request for an actor.
/// </summary>
/// <param name="eTag">The actor's last-known ETag value.</param>
/// <param name="results">The ordered collection of results.</param>
public class ReadResponse(string eTag, IReadOnlyList<ActorReadResult> results)
{
    /// <summary>
    /// Gets the version of the state update.
    /// </summary>
    [JsonPropertyName("etag")]
    public string ETag { get; } = eTag;

    /// <summary>
    /// Gets the ordered collection of read operation results.
    /// </summary>
    [JsonPropertyName("results")]
    public IReadOnlyList<ActorReadResult> Results { get; } = results;
}
