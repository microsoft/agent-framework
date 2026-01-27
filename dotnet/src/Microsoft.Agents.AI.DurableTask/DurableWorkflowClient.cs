// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides a durable task-based implementation of <see cref="IWorkflowClient"/> for running
/// workflows as durable orchestrations.
/// </summary>
/// <remarks>
/// This class wraps the <see cref="DurableTaskClient"/> and provides methods to run workflows
/// without requiring the client to be passed explicitly. Register this class in DI using
/// <see cref="DurableWorkflowServiceCollectionExtensions.ConfigureDurableWorkflows"/>.
/// </remarks>
public sealed class DurableWorkflowClient : IWorkflowClient
{
    private readonly DurableTaskClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowClient"/> class.
    /// </summary>
    /// <param name="client">The durable task client for orchestration operations.</param>
    public DurableWorkflowClient(DurableTaskClient client)
    {
        this._client = client ?? throw new ArgumentNullException(nameof(client));
    }

    /// <inheritdoc/>
    public ValueTask<IRun> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
        => DurableWorkflow.RunAsync(workflow, input, this._client, runId, cancellationToken);

    /// <inheritdoc/>
    public ValueTask<IRun> RunAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        => DurableWorkflow.RunAsync(workflow, input, this._client, runId, cancellationToken);

    /// <inheritdoc/>
    public ValueTask<IStreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
        => DurableWorkflow.StreamAsync(workflow, input, this._client, runId, cancellationToken);

    /// <inheritdoc/>
    public ValueTask<IStreamingRun> StreamAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        => DurableWorkflow.StreamAsync(workflow, input, this._client, runId, cancellationToken);

    /// <summary>
    /// Attaches to an existing workflow orchestration instance.
    /// </summary>
    /// <remarks>
    /// This is a durable-specific method not available on <see cref="IWorkflowClient"/>.
    /// </remarks>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflowName">The name of the workflow being executed.</param>
    /// <returns>An <see cref="IRun"/> that can be used to monitor the workflow execution.</returns>
    public IRun Attach(string instanceId, string workflowName)
        => DurableWorkflow.Attach(instanceId, workflowName, this._client);

    /// <summary>
    /// Attaches to an existing workflow orchestration instance for streaming.
    /// </summary>
    /// <remarks>
    /// This is a durable-specific method not available on <see cref="IWorkflowClient"/>.
    /// </remarks>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflow">The workflow being executed.</param>
    /// <returns>An <see cref="IStreamingRun"/> that can be used to stream workflow events.</returns>
    public IStreamingRun AttachStream(string instanceId, Workflow workflow)
        => DurableWorkflow.AttachStream(instanceId, workflow, this._client);
}
