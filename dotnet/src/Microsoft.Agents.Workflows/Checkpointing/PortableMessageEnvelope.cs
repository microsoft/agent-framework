// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class PortableMessageEnvelope
{
    public TypeId MessageType { get; }
    public PortableValue Message { get; }
    public string? TargetId { get; }

    [JsonConstructor]
    internal PortableMessageEnvelope(TypeId messageType, PortableValue message, string? targetId)
    {
        this.MessageType = messageType;
        this.Message = message;
        this.TargetId = targetId;
    }

    public PortableMessageEnvelope(MessageEnvelope envelope)
    {
        this.MessageType = envelope.MessageType;
        this.Message = new PortableValue(envelope.Message);
        this.TargetId = envelope.TargetId;
    }

    public MessageEnvelope ToMessageEnvelope()
    {
        return new MessageEnvelope(this.Message, this.MessageType, this.TargetId);
    }
}
