// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a running instance of a workflow.
/// </summary>
public interface IWorkflowRun
{
    /// <summary>
    /// Gets the unique identifier for the run.
    /// </summary>
    /// <remarks>
    /// This identifier can be provided at the start of the run, or auto-generated.
    /// For durable runs, this corresponds to the orchestration instance ID.
    /// </remarks>
    string RunId { get; }

    /// <summary>
    /// Gets all events that have been emitted by the workflow.
    /// </summary>
    IEnumerable<WorkflowEvent> OutgoingEvents { get; }

    /// <summary>
    /// Gets the number of events emitted since the last access to <see cref="NewEvents"/>.
    /// </summary>
    int NewEventCount { get; }

    /// <summary>
    /// Gets all events emitted by the workflow since the last access to this property.
    /// </summary>
    /// <remarks>
    /// Each access to this property advances the bookmark, so subsequent accesses
    /// will only return events emitted after the previous access.
    /// </remarks>
    IEnumerable<WorkflowEvent> NewEvents { get; }
}
