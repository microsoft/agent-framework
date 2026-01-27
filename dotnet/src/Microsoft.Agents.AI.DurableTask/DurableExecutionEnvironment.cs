// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides a DI-friendly execution environment for running workflows as durable orchestrations.
/// </summary>
/// <remarks>
/// This class wraps the <see cref="DurableTaskClient"/> and provides methods to run workflows
/// without requiring the client to be passed explicitly. Register this class in DI using
/// <see cref="DurableWorkflowServiceCollectionExtensions.ConfigureDurableWorkflows"/>.
/// </remarks>
public sealed class DurableExecutionEnvironment
{
    private readonly DurableTaskClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableExecutionEnvironment"/> class.
    /// </summary>
    /// <param name="client">The durable task client for orchestration operations.</param>
    public DurableExecutionEnvironment(DurableTaskClient client)
    {
        this._client = client ?? throw new ArgumentNullException(nameof(client));
    }

    /// <summary>
    /// Runs a workflow as a durable orchestration and returns a handle to monitor its execution.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    /// <exception cref="ArgumentNullException">Thrown when workflow is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public ValueTask<IRun> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
        => DurableWorkflow.RunAsync(workflow, input, this._client, instanceId, cancellationToken);

    /// <summary>
    /// Runs a workflow as a durable orchestration with string input.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    public ValueTask<IRun> RunAsync(
        Workflow workflow,
        string input,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        => DurableWorkflow.RunAsync(workflow, input, this._client, instanceId, cancellationToken);

    /// <summary>
    /// Starts a workflow as a durable orchestration and returns a streaming handle to watch events.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    /// <exception cref="ArgumentNullException">Thrown when workflow is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public ValueTask<IStreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
        => DurableWorkflow.StreamAsync(workflow, input, this._client, instanceId, cancellationToken);

    /// <summary>
    /// Starts a workflow as a durable orchestration with string input and returns a streaming handle.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    public ValueTask<IStreamingRun> StreamAsync(
        Workflow workflow,
        string input,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        => DurableWorkflow.StreamAsync(workflow, input, this._client, instanceId, cancellationToken);

    /// <summary>
    /// Attaches to an existing workflow orchestration instance.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflowName">The name of the workflow being executed.</param>
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    public IRun Attach(string instanceId, string workflowName)
        => DurableWorkflow.Attach(instanceId, workflowName, this._client);

    /// <summary>
    /// Attaches to an existing workflow orchestration instance for streaming.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflow">The workflow being executed.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    public IStreamingRun AttachStream(string instanceId, Workflow workflow)
        => DurableWorkflow.AttachStream(instanceId, workflow, this._client);
}
