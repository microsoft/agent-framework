// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Behaviors;

/// <summary>
/// Represents a behavior that wraps workflow execution, allowing custom logic before and after workflow operations.
/// </summary>
/// <remarks>
/// Implement this interface to add cross-cutting concerns like logging, telemetry, validation, or performance monitoring
/// at the workflow level. Multiple behaviors can be chained together to form a pipeline.
/// </remarks>
public interface IWorkflowBehavior
{
    /// <summary>
    /// Handles workflow execution with the ability to execute logic before and after the next behavior in the pipeline.
    /// </summary>
    /// <typeparam name="TResult">The result type of the workflow operation.</typeparam>
    /// <param name="context">The context containing information about the current workflow execution.</param>
    /// <param name="continuation">The delegate to invoke the next behavior in the pipeline or the actual workflow operation.</param>
    /// <param name="cancellationToken">The cancellation token to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation, with the result of the workflow operation.</returns>
    ValueTask<TResult> HandleAsync<TResult>(
        WorkflowBehaviorContext context,
        WorkflowBehaviorContinuation<TResult> continuation,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Represents the continuation in the workflow behavior pipeline.
/// </summary>
/// <typeparam name="TResult">The result type of the operation.</typeparam>
/// <param name="cancellationToken">The cancellation token to monitor for cancellation requests.</param>
/// <returns>A task representing the asynchronous operation.</returns>
public delegate ValueTask<TResult> WorkflowBehaviorContinuation<TResult>(CancellationToken cancellationToken);

/// <summary>
/// Provides context information for workflow behaviors.
/// </summary>
public sealed class WorkflowBehaviorContext
{
    /// <summary>
    /// Gets the name of the workflow being executed.
    /// </summary>
    public string WorkflowName { get; init; } = string.Empty;

    /// <summary>
    /// Gets the optional description of the workflow.
    /// </summary>
    public string? WorkflowDescription { get; init; }

    /// <summary>
    /// Gets the unique identifier for this workflow execution run.
    /// </summary>
    public string RunId { get; init; } = string.Empty;

    /// <summary>
    /// Gets the identifier of the starting executor in the workflow.
    /// </summary>
    public string StartExecutorId { get; init; } = string.Empty;

    /// <summary>
    /// Gets the stage of workflow execution.
    /// </summary>
    public WorkflowStage Stage { get; init; }

    /// <summary>
    /// Gets optional custom properties that can be used to pass additional context.
    /// </summary>
    public IReadOnlyDictionary<string, object>? Properties { get; init; }
}

/// <summary>
/// Represents the stage of workflow execution.
/// </summary>
public enum WorkflowStage
{
    /// <summary>
    /// The workflow is starting execution.
    /// </summary>
    Starting,

    /// <summary>
    /// The workflow is ending execution.
    /// </summary>
    Ending
}
