// Copyright (c) Microsoft. All rights reserved.

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

        DurableWorkflowInput<TInput> workflowInput = new() { Input = input };

        string instanceId = await this._client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name),
            input: workflowInput,
            options: runId is not null ? new StartOrchestrationOptions(runId) : null,
            cancellation: cancellationToken).ConfigureAwait(false);

        return new DurableWorkflowRun(this._client, instanceId, workflow.Name);
    }

    /// <inheritdoc/>
    public ValueTask<IWorkflowRun> RunAsync(
        Workflow workflow,
        string input,
        string? runId = null,
        CancellationToken cancellationToken = default)
        => this.RunAsync<string>(workflow, input, runId, cancellationToken);
}
