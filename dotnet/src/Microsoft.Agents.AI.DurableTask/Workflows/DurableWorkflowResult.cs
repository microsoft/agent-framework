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

    /// <summary>
    /// Gets or sets the typed messages to forward to connected executors in the parent workflow.
    /// </summary>
    /// <remarks>
    /// When this workflow runs as a sub-orchestration, these messages are propagated to the
    /// parent workflow and routed to successor executors via the edge map.
    /// </remarks>
    public List<TypedPayload> SentMessages { get; set; } = [];

    /// <summary>
    /// Gets or sets a value indicating whether the workflow was halted by an executor.
    /// </summary>
    /// <remarks>
    /// When this workflow runs as a sub-orchestration, this flag is propagated to the
    /// parent workflow so halt semantics are preserved across nesting levels.
    /// </remarks>
    public bool HaltRequested { get; set; }
}
