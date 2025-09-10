// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Actor;

/// <summary>
/// Input for sending message to the actor.
/// </summary>
public sealed class SendMessageRequest(string method, JsonElement @params)
{
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
