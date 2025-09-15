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
        this.ActionInvokeEvents = workflowEvents.OfType<DeclarativeActionInvokeEvent>().ToImmutableList();
        this.ActionCompleteEvents = workflowEvents.OfType<DeclarativeActionCompleteEvent>().ToImmutableList();
    }

    public ImmutableList<WorkflowEvent> Events { get; }
    public IImmutableDictionary<Type, int> EventCounts { get; }
    public ImmutableList<DeclarativeActionInvokeEvent> ActionInvokeEvents { get; }
    public ImmutableList<DeclarativeActionCompleteEvent> ActionCompleteEvents { get; private set; }
}
