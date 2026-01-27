// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events,
/// supporting resumption with responses to external requests.
/// </summary>
/// <remarks>
/// This interface defines the common contract for workflow runs across different execution
/// environments (in-process, durable, etc.). Implementations provide the mechanism to
/// interact with running workflows, send responses, and access emitted events.
/// </remarks>
public interface IRun : IAsyncDisposable
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

    /// <summary>
    /// Sends an external response to the workflow.
    /// </summary>
    /// <param name="response">The external response to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask SendResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default);
}
