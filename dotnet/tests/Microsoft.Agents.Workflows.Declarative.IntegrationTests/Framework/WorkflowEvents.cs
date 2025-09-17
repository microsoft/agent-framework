// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Immutable;
using System.Linq;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

internal sealed class WorkflowEvents
{
    public WorkflowEvents(ImmutableList<WorkflowEvent> workflowEvents)
    {
        this.Events = workflowEvents;
        this.EventCounts = workflowEvents.GroupBy(e => e.GetType()).ToImmutableDictionary(e => e.Key, e => e.Count());
        this.ActionInvokeEvents = workflowEvents.OfType<DeclarativeActionInvokedEvent>().ToImmutableList();
        this.ActionCompleteEvents = workflowEvents.OfType<DeclarativeActionCompletedEvent>().ToImmutableList();
    }

    public ImmutableList<WorkflowEvent> Events { get; }
    public IImmutableDictionary<Type, int> EventCounts { get; }
    public ImmutableList<DeclarativeActionInvokedEvent> ActionInvokeEvents { get; }
    public ImmutableList<DeclarativeActionCompletedEvent> ActionCompleteEvents { get; private set; }
}
