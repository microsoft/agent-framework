// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

internal sealed class WorkflowEvents
{
    public WorkflowEvents(IReadOnlyList<WorkflowEvent> workflowEvents)
    {
        this.Events = workflowEvents;
        this.EventCounts = workflowEvents.GroupBy(e => e.GetType()).ToDictionary(e => e.Key, e => e.Count());
        this.ActionInvokeEvents = workflowEvents.OfType<DeclarativeActionInvokedEvent>().ToList();
        this.ActionCompleteEvents = workflowEvents.OfType<DeclarativeActionCompletedEvent>().ToList();
    }

    public IReadOnlyList<WorkflowEvent> Events { get; }
    public IReadOnlyDictionary<Type, int> EventCounts { get; }
    public IReadOnlyList<DeclarativeActionInvokedEvent> ActionInvokeEvents { get; }
    public IReadOnlyList<DeclarativeActionCompletedEvent> ActionCompleteEvents { get; }
}
