// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Base class for request messages sent to actors.
/// </summary>
public sealed class ActorRequestMessage(string MessageId) : ActorMessage
{
    /// <inheritdoc/>
    public override ActorMessageType Type => ActorMessageType.Request;

    /// <summary>
    /// Gets or sets the actor ID of the sender.
    /// </summary>
    [JsonPropertyName("sender")]
    public ActorId? SenderId { get; init; }

    /// <summary>
    /// Gets or sets the unique identifier for the request.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string MessageId { get; } = MessageId;

    /// <summary>
    /// Name of the method to invoke.
    /// </summary>
    [JsonPropertyName("method")]
    public string? Method { get; init; }

    /// <summary>
    /// Optional parameters for the method invocation.
    /// </summary>
    [JsonPropertyName("params")]
    public JsonElement Params { get; init; }
}
