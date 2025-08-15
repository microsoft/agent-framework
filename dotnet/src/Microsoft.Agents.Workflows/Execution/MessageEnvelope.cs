// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class MessageEnvelope(object message, string? targetId = null)
{
    public object Message => message;
    public string? TargetId => targetId;
}
