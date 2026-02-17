// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Wraps the orchestration output to include both the workflow result and accumulated events.
/// </summary>
/// <remarks>
/// The Durable Task framework clears <c>SerializedCustomStatus</c> when an orchestration
/// completes. To ensure streaming clients can retrieve events even after completion,
/// the accumulated events are embedded in the orchestration output alongside the result.
/// </remarks>
internal sealed class DurableWorkflowResult
{
    /// <summary>
    /// Gets or sets the serialized result of the workflow execution.
    /// </summary>
    public string? Result { get; set; }

    /// <summary>
    /// Gets or sets the serialized workflow events emitted during execution.
    /// </summary>
    public List<string> Events { get; set; } = [];
}
