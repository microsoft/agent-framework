// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Event raised when an executor requests the workflow to halt via <see cref="IWorkflowContext.RequestHaltAsync"/>.
/// </summary>
/// <remarks>
/// This is the durable equivalent of the internal RequestHaltEvent since that class is not accessible
/// from outside the Workflows assembly.
/// </remarks>
public sealed class DurableHaltRequestedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableHaltRequestedEvent"/> class.
    /// </summary>
    /// <param name="executorId">The ID of the executor that requested the halt.</param>
    public DurableHaltRequestedEvent(string executorId) : base($"Halt requested by {executorId}")
    {
        this.ExecutorId = executorId;
    }

    /// <summary>
    /// Gets the ID of the executor that requested the halt.
    /// </summary>
    public string ExecutorId { get; }
}
