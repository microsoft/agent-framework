// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Behaviors;

/// <summary>
/// Internal class that manages the execution of behavior pipelines for workflows and executors.
/// </summary>
internal sealed class BehaviorPipeline
{
    private readonly List<IExecutorBehavior> _executorBehaviors;
    private readonly List<IWorkflowBehavior> _workflowBehaviors;

    /// <summary>
    /// Initializes a new instance of the <see cref="BehaviorPipeline"/> class.
    /// </summary>
    /// <param name="executorBehaviors">The collection of executor behaviors to execute.</param>
    /// <param name="workflowBehaviors">The collection of workflow behaviors to execute.</param>
    public BehaviorPipeline(
        IEnumerable<IExecutorBehavior> executorBehaviors,
        IEnumerable<IWorkflowBehavior> workflowBehaviors)
    {
        this._executorBehaviors = executorBehaviors.ToList();
        this._workflowBehaviors = workflowBehaviors.ToList();
    }

    /// <summary>
    /// Gets a value indicating whether any executor behaviors are registered.
    /// </summary>
    public bool HasExecutorBehaviors => this._executorBehaviors.Count > 0;

    /// <summary>
    /// Gets a value indicating whether any workflow behaviors are registered.
    /// </summary>
    public bool HasWorkflowBehaviors => this._workflowBehaviors.Count > 0;

    /// <summary>
    /// Executes the executor behavior pipeline.
    /// </summary>
    /// <param name="context">The context for the executor execution.</param>
    /// <param name="finalHandler">The final handler to execute after all behaviors.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The result of the executor execution.</returns>
    public async ValueTask<object?> ExecuteExecutorPipelineAsync(
        ExecutorBehaviorContext context,
        Func<CancellationToken, ValueTask<object?>> finalHandler,
        CancellationToken cancellationToken)
    {
        if (this._executorBehaviors.Count == 0)
        {
            return await finalHandler(cancellationToken).ConfigureAwait(false);
        }

        // Build chain from end to start (reverse order)
        ExecutorBehaviorContinuation pipeline = new(finalHandler);

        for (int i = this._executorBehaviors.Count - 1; i >= 0; i--)
        {
            var behavior = this._executorBehaviors[i];
            var continuation = pipeline;
            pipeline = new ExecutorBehaviorContinuation((ct) => ExecuteBehaviorWithErrorHandlingAsync(behavior, context, continuation, ct));
        }

        return await pipeline(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Executes the workflow behavior pipeline.
    /// </summary>
    /// <typeparam name="TResult">The result type of the workflow operation.</typeparam>
    /// <param name="context">The context for the workflow execution.</param>
    /// <param name="finalHandler">The final handler to execute after all behaviors.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The result of the workflow execution.</returns>
    public async ValueTask<TResult> ExecuteWorkflowPipelineAsync<TResult>(
        WorkflowBehaviorContext context,
        Func<CancellationToken, ValueTask<TResult>> finalHandler,
        CancellationToken cancellationToken)
    {
        if (this._workflowBehaviors.Count == 0)
        {
            return await finalHandler(cancellationToken).ConfigureAwait(false);
        }

        // Build chain from end to start (reverse order)
        WorkflowBehaviorContinuation<TResult> pipeline = new(finalHandler);

        for (int i = this._workflowBehaviors.Count - 1; i >= 0; i--)
        {
            var behavior = this._workflowBehaviors[i];
            var continuation = pipeline;
            pipeline = new WorkflowBehaviorContinuation<TResult>((ct) => ExecuteBehaviorWithErrorHandlingAsync(behavior, context, continuation, ct));
        }

        return await pipeline(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Executes an executor behavior with error handling.
    /// </summary>
    private static async ValueTask<object?> ExecuteBehaviorWithErrorHandlingAsync(
        IExecutorBehavior behavior,
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken)
    {
        try
        {
            return await behavior.HandleAsync(context, continuation, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not BehaviorExecutionException)
        {
            throw new BehaviorExecutionException(
                behavior.GetType().FullName ?? "Unknown",
                context.Stage.ToString(),
                ex
            );
        }
    }

    /// <summary>
    /// Executes a workflow behavior with error handling.
    /// </summary>
    private static async ValueTask<TResult> ExecuteBehaviorWithErrorHandlingAsync<TResult>(
        IWorkflowBehavior behavior,
        WorkflowBehaviorContext context,
        WorkflowBehaviorContinuation<TResult> continuation,
        CancellationToken cancellationToken)
    {
        try
        {
            return await behavior.HandleAsync(context, continuation, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not BehaviorExecutionException)
        {
            throw new BehaviorExecutionException(
                behavior.GetType().FullName ?? "Unknown",
                context.Stage.ToString(),
                ex
            );
        }
    }
}
