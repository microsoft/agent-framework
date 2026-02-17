// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Behaviors;

/// <summary>
/// Represents a behavior that wraps executor step execution, allowing custom logic before and after executor operations.
/// </summary>
/// <remarks>
/// Implement this interface to add cross-cutting concerns like logging, telemetry, validation, or performance monitoring
/// at the executor level. Multiple behaviors can be chained together to form a pipeline.
/// Behaviors execute once per executor invocation. Logic placed before <c>await continuation()</c> runs before the executor;
/// logic placed after runs once the executor (and any subsequent behaviors) has completed.
/// </remarks>
public interface IExecutorBehavior
{
    /// <summary>
    /// Handles executor execution with the ability to execute logic before and after the next behavior in the pipeline.
    /// </summary>
    /// <param name="context">The context containing information about the current executor execution.</param>
    /// <param name="continuation">The delegate to invoke the next behavior in the pipeline or the actual executor operation.</param>
    /// <param name="cancellationToken">The cancellation token to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation, with the result of the executor operation.</returns>
    ValueTask<object?> HandleAsync(
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Represents the continuation in the executor behavior pipeline.
/// </summary>
/// <param name="cancellationToken">The cancellation token to monitor for cancellation requests.</param>
/// <returns>A task representing the asynchronous operation with the executor result.</returns>
public delegate ValueTask<object?> ExecutorBehaviorContinuation(CancellationToken cancellationToken);

/// <summary>
/// Provides context information for executor behaviors.
/// </summary>
public sealed class ExecutorBehaviorContext
{
    /// <summary>
    /// Gets the identifier of the executor being invoked.
    /// </summary>
    public string ExecutorId { get; init; } = string.Empty;

    /// <summary>
    /// Gets the type of the executor being invoked.
    /// </summary>
    public required Type ExecutorType { get; init; }

    /// <summary>
    /// Gets the message being processed by the executor.
    /// </summary>
    public required object Message { get; init; }

    /// <summary>
    /// Gets the type of the message being processed.
    /// </summary>
    public required Type MessageType { get; init; }

    /// <summary>
    /// Gets the unique identifier for the workflow execution run.
    /// </summary>
    public string RunId { get; init; } = string.Empty;

    /// <summary>
    /// Gets the stage of executor execution.
    /// </summary>
    public ExecutorStage Stage { get; init; }

    /// <summary>
    /// Gets the workflow context for this execution.
    /// </summary>
    public required IWorkflowContext WorkflowContext { get; init; }

    /// <summary>
    /// Gets the trace context for distributed tracing.
    /// </summary>
    public IReadOnlyDictionary<string, string>? TraceContext { get; init; }

    /// <summary>
    /// Gets optional custom properties that can be used to pass additional context.
    /// </summary>
    public IReadOnlyDictionary<string, object>? Properties { get; init; }
}

/// <summary>
/// Represents the stage of executor execution.
/// </summary>
public enum ExecutorStage
{
    /// <summary>
    /// Before the executor begins processing the message. Behaviors are invoked once per executor call.
    /// To perform logic after the executor completes, place code after the <c>await continuation()</c> call
    /// in <see cref="IExecutorBehavior.HandleAsync"/>.
    /// </summary>
    PreExecution
}
