// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Defines a client for running and managing workflow executions.
/// </summary>
/// <remarks>
/// This interface provides a unified API for running workflows across different execution
/// environments. Implementations handle the underlying infrastructure details, allowing
/// callers to work with workflows without knowledge of the specific execution backend.
/// </remarks>
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
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    ValueTask<IRun> RunAsync<TInput>(
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
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    ValueTask<IRun> RunAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Starts a workflow and returns a streaming handle to watch events.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="runId">Optional identifier for the run. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    ValueTask<IStreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull;

    /// <summary>
    /// Starts a workflow with string input and returns a streaming handle to watch events.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="runId">Optional identifier for the run. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    ValueTask<IStreamingRun> StreamAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default);
}
