// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow completes execution.
/// </summary>
internal sealed class RequestHaltEvent : WorkflowEvent
{
    internal RequestHaltEvent(object? result = null) : base(result)
    { }
}
