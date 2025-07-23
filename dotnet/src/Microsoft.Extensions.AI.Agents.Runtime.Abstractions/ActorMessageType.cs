// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Specifies the type of actor message.
/// </summary>
public enum ActorMessageType
{
    /// <summary>
    /// Represents a request message sent to an actor.
    /// </summary>
    [JsonStringEnumMemberName("request")]
    Request,

    /// <summary>
    /// Represents a response message sent from an actor.
    /// </summary>
    [JsonStringEnumMemberName("response")]
    Response
}
