// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a request to be sent to an actor.
/// </summary>
public sealed class ActorRequest(ActorId actorId, string messageId, string method, JsonElement @params)
{
    /// <summary>
    /// Gets or sets the identifier of the target actor.
    /// </summary>
    [JsonPropertyName("actorId")]
    public ActorId ActorId { get; } = actorId;

    /// <summary>
    /// Gets or sets the unique identifier for this request.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string MessageId { get; } = messageId;

    /// <summary>
    /// Gets or sets the method name to invoke on the actor.
    /// </summary>
    [JsonPropertyName("method")]
    public string Method { get; } = method;

    /// <summary>
    /// Gets or sets the parameters for the method invocation.
    /// </summary>
    [JsonPropertyName("params")]
    public JsonElement Params { get; } = @params;
}
