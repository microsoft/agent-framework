// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class MessageEnvelope(object message, TypeId? declaredType = null, string? targetId = null)
{
    public TypeId MessageType => declaredType ?? new(message.GetType());
    public object Message => message;
    public string? TargetId => targetId;

    internal MessageEnvelope(object message, Type declaredType, string? targetId = null)
        : this(message, new TypeId(declaredType), targetId)
    {
        if (!declaredType.IsAssignableFrom(message.GetType()))
        {
            throw new ArgumentException($"The declared type {declaredType} is not compatible with the message instance of type {message.GetType()}");
        }
    }
}
