// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a response handle for an actor request, providing access to the result and status updates.
/// </summary>
public class ActorResponse
{
    /// <summary>
    /// Gets the identifier of the actor that is processing the request.
    /// </summary>
    [JsonPropertyName("actorId")]
    public ActorId ActorId { get; init; }

    /// <summary>
    /// Gets the unique identifier of the message/request.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string? MessageId { get; init; }

    /// <summary>
    /// Gets the response data from the actor.
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement Data { get; init; }

    /// <summary>
    /// Gets or sets the current status of the request.
    /// </summary>
    [JsonPropertyName("status")]
    public RequestStatus Status { get; init; }
}
