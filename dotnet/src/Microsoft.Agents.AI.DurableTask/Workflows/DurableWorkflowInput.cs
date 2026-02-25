// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents the input envelope for a durable workflow orchestration.
/// </summary>
/// <typeparam name="TInput">The type of the workflow input.</typeparam>
internal sealed class DurableWorkflowInput<TInput>
    where TInput : notnull
{
    /// <summary>
    /// Gets the workflow input data.
    /// </summary>
    public required TInput Input { get; init; }

    /// <summary>
    /// Gets or sets the W3C traceparent of the client-side workflow.run span.
    /// Propagated through the orchestration to activity workers so that executor spans
    /// appear as children of workflow.run in the trace hierarchy.
    /// </summary>
    public string? TraceParent { get; set; }
}
