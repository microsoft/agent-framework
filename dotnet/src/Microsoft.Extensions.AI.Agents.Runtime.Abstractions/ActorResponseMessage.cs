// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Base class for response messages sent from actors.
/// </summary>
public sealed class ActorResponseMessage(string MessageId) : ActorMessage
{
    /// <inheritdoc/>
    public override ActorMessageType Type => ActorMessageType.Response;

    /// <summary>
    /// Gets or sets the actor ID of the sender.
    /// </summary>
    [JsonPropertyName("senderId")]
    public ActorId SenderId { get; init; }

    /// <summary>
    /// Gets or sets the unique identifier for the request.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string MessageId { get; } = MessageId;

    /// <summary>
    /// Gets or sets the status of the request.
    /// </summary>
    [JsonPropertyName("status")]
    public RequestStatus Status { get; init; }

    /// <summary>
    /// Gets or sets the response data (result or error information).
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement Data { get; init; }
}
