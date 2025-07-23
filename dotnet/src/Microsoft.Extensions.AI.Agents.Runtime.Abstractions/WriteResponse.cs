// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the response of a write request for an actor.
/// </summary>
/// <param name="eTag">The actor's updated ETag value after the write operation.</param>
/// <param name="success">Whether the write operation was successful.</param>
public class WriteResponse(string eTag, bool success)
{
    /// <summary>
    /// Gets the version of the state update.
    /// </summary>
    [JsonPropertyName("etag")]
    public string ETag { get; } = eTag;

    /// <summary>
    /// Whether the write operation was successful.
    /// </summary>
    /// <remarks>
    /// If <c>false</c>, the write operation may have failed due to a concurrency conflict or other issue.
    /// In either case the <see cref="ETag"/> property will contain the last known ETag value of the actor's state.
    /// </remarks>
    [JsonPropertyName("success")]
    public bool Success { get; } = success;
}
