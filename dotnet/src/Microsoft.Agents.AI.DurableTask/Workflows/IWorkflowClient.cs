// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Defines a client for running and managing workflow executions.
/// </summary>
public interface IWorkflowClient
{
    /// <summary>
    /// Runs a workflow and returns a handle to monitor its execution.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="runId">Optional identifier for the run. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IWorkflowRun"/> that can be used to monitor the workflow execution.</returns>
    ValueTask<IWorkflowRun> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull;

    /// <summary>
    /// Runs a workflow with string input and returns a handle to monitor its execution.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="runId">Optional identifier for the run. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IWorkflowRun"/> that can be used to monitor the workflow execution.</returns>
    ValueTask<IWorkflowRun> RunAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default);
}
