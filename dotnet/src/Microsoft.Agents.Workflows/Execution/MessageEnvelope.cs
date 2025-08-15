// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class MessageEnvelope(object message, Type? declaredType = null, string? targetId = null)
{
    public Type MessageType => declaredType ?? message.GetType();
    public object Message => message;
    public string? TargetId => targetId;
}
