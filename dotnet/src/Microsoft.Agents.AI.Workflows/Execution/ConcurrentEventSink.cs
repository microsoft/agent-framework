// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IEventSink
{
    ValueTask EnqueueAsync(WorkflowEvent workflowEvent);
}

internal class ConcurrentEventSink : IEventSink
{
    public ValueTask EnqueueAsync(WorkflowEvent workflowEvent)
    {
        return this.EventRaised?.Invoke(this, Throw.IfNull(workflowEvent)) ?? default;
    }

    public event Func<object?, WorkflowEvent, ValueTask>? EventRaised;
}
