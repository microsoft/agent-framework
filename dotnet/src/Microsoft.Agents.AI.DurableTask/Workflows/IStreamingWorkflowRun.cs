// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a workflow run that supports streaming workflow events as they occur.
/// </summary>
/// <remarks>
/// This interface defines the contract for streaming workflow runs in durable execution
/// environments. Implementations provide real-time access to workflow events.
/// </remarks>
public interface IStreamingWorkflowRun
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
    /// Asynchronously streams workflow events as they occur during workflow execution.
    /// </summary>
    /// <remarks>
    /// This method yields <see cref="WorkflowEvent"/> instances in real time as the workflow
    /// progresses. The stream completes when the workflow completes, fails, or is terminated.
    /// Events are delivered in the order they are raised.
    /// </remarks>
    /// <param name="cancellationToken">
    /// A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.
    /// If cancellation is requested, the stream will end and no further events will be yielded.
    /// </param>
    /// <returns>
    /// An asynchronous stream of <see cref="WorkflowEvent"/> objects representing significant
    /// workflow state changes.
    /// </returns>
    IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(CancellationToken cancellationToken = default);
}
