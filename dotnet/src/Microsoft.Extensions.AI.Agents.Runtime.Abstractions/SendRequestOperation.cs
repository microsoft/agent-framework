// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents an operation to send a request message to another actor.
/// </summary>
/// <param name="Message">The request message to send.</param>
public sealed class SendRequestOperation(ActorRequestMessage Message) : ActorMessageWriteOperation
{
    /// <summary>
    /// Gets the message to send.
    /// </summary>
    [JsonPropertyName("message")]
    public ActorRequestMessage Message { get; } = Message;

    /// <summary>
    /// Gets the type of the write operation.
    /// </summary>
    public override ActorWriteOperationType Type => ActorWriteOperationType.SendRequest;
}
