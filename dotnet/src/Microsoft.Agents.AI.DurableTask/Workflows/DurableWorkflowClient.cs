// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Provides a durable task-based implementation of <see cref="IWorkflowClient"/> for running
/// workflows as durable orchestrations.
/// </summary>
internal sealed class DurableWorkflowClient : IWorkflowClient
{
    private readonly DurableTaskClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowClient"/> class.
    /// </summary>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is null.</exception>
    public DurableWorkflowClient(DurableTaskClient client)
    {
        ArgumentNullException.ThrowIfNull(client);
        this._client = client;
    }

    /// <inheritdoc/>
    public async ValueTask<IWorkflowRun> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        // Start workflow.run at the client level so its span ID is stable across orchestrator
        // replays. The Durable Task orchestrator re-executes from the top on each replay,
        // creating new Activity objects that are abandoned when the method suspends. By creating
        // workflow.run here and propagating its context via TraceParent, activity worker spans
        // consistently reference a properly exported parent span.
        Activity? runActivity = DurableWorkflowInstrumentation.ActivitySource.StartActivity("workflow.run");
        runActivity?.SetTag("workflow.id", workflow.StartExecutorId)
            .SetTag("workflow.name", workflow.Name);

        DurableWorkflowInput<TInput> workflowInput = new()
        {
            Input = input,
            TraceParent = runActivity?.Id ?? Activity.Current?.Id
        };

        string instanceId = await this._client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name),
            input: workflowInput,
            options: runId is not null ? new StartOrchestrationOptions(runId) : null,
            cancellation: cancellationToken).ConfigureAwait(false);

        runActivity?.SetTag("run.id", instanceId);

        return new DurableWorkflowRun(this._client, instanceId, workflow.Name, runActivity);
    }

    /// <inheritdoc/>
    public ValueTask<IWorkflowRun> RunAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        => this.RunAsync<string>(workflow, input, runId, cancellationToken);

    /// <inheritdoc/>
    public async ValueTask<IStreamingWorkflowRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        Activity? runActivity = DurableWorkflowInstrumentation.ActivitySource.StartActivity("workflow.run");
        runActivity?.SetTag("workflow.id", workflow.StartExecutorId)
            .SetTag("workflow.name", workflow.Name);

        DurableWorkflowInput<TInput> workflowInput = new()
        {
            Input = input,
            TraceParent = runActivity?.Id ?? Activity.Current?.Id
        };

        string instanceId = await this._client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name),
            input: workflowInput,
            options: runId is not null ? new StartOrchestrationOptions(runId) : null,
            cancellation: cancellationToken).ConfigureAwait(false);

        runActivity?.SetTag("run.id", instanceId);

        return new DurableStreamingWorkflowRun(this._client, instanceId, workflow, runActivity);
    }

    /// <inheritdoc/>
    public ValueTask<IStreamingWorkflowRun> StreamAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        => this.StreamAsync<string>(workflow, input, runId, cancellationToken);
}
