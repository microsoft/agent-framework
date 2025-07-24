// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

// External (client) interface.

/// <summary>
/// Represents an update to an actor request's status and data.
/// </summary>
public sealed class ActorRequestUpdate(RequestStatus status, JsonElement data)
{
    /// <summary>
    /// Gets the updated status of the request.
    /// </summary>
    [JsonPropertyName("status")]
    public RequestStatus Status { get; } = status;

    /// <summary>
    /// Gets the updated data associated with the request.
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement Data { get; } = data;
}
