// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides methods to run workflows as durable orchestrations.
/// </summary>
public static class DurableWorkflow
{
    /// <summary>
    /// Runs a workflow as a durable orchestration and returns a handle to monitor its execution.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="DurableRun"/> that can be used to monitor the workflow execution.</returns>
    /// <exception cref="ArgumentNullException">Thrown when workflow or client is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public static async ValueTask<DurableRun> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        DurableTaskClient client,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        ArgumentNullException.ThrowIfNull(workflow);
        ArgumentNullException.ThrowIfNull(client);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name);
        string actualInstanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: orchestrationName,
            input: input,
            cancellation: cancellationToken).ConfigureAwait(false);

        return new DurableRun(client, actualInstanceId, workflow.Name);
    }

    /// <summary>
    /// Runs a workflow as a durable orchestration with string input.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="DurableRun"/> that can be used to monitor the workflow execution.</returns>
    public static ValueTask<DurableRun> RunAsync(
        Workflow workflow,
        string input,
        DurableTaskClient client,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        => RunAsync<string>(workflow, input, client, instanceId, cancellationToken);

    /// <summary>
    /// Starts a workflow as a durable orchestration and returns a streaming handle to watch events.
    /// </summary>
    /// <typeparam name="TInput">The type of the input to the workflow.</typeparam>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The input to pass to the workflow's starting executor.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration. If not provided, a new ID will be generated.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="DurableStreamingRun"/> that can be used to stream workflow events.</returns>
    /// <exception cref="ArgumentNullException">Thrown when workflow or client is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public static async ValueTask<DurableStreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        DurableTaskClient client,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        ArgumentNullException.ThrowIfNull(workflow);
        ArgumentNullException.ThrowIfNull(client);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Name);
        string actualInstanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: orchestrationName,
            input: input,
            cancellation: cancellationToken).ConfigureAwait(false);

        return new DurableStreamingRun(client, actualInstanceId, workflow);
    }

    /// <summary>
    /// Starts a workflow as a durable orchestration with string input and returns a streaming handle.
    /// </summary>
    /// <param name="workflow">The workflow to execute.</param>
    /// <param name="input">The string input to pass to the workflow.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">Optional instance ID for the orchestration.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="DurableStreamingRun"/> that can be used to stream workflow events.</returns>
    public static ValueTask<DurableStreamingRun> StreamAsync(
        Workflow workflow,
        string input,
        DurableTaskClient client,
        string? instanceId = null,
        CancellationToken cancellationToken = default)
        => StreamAsync<string>(workflow, input, client, instanceId, cancellationToken);

    /// <summary>
    /// Attaches to an existing workflow orchestration instance.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflowName">The name of the workflow being executed.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <returns>A <see cref="DurableRun"/> that can be used to monitor the workflow execution.</returns>
    public static DurableRun Attach(
        string instanceId,
        string workflowName,
        DurableTaskClient client)
    {
        ArgumentException.ThrowIfNullOrEmpty(instanceId);
        ArgumentException.ThrowIfNullOrEmpty(workflowName);
        ArgumentNullException.ThrowIfNull(client);

        return new DurableRun(client, instanceId, workflowName);
    }

    /// <summary>
    /// Attaches to an existing workflow orchestration instance for streaming.
    /// </summary>
    /// <param name="instanceId">The instance ID of the orchestration to attach to.</param>
    /// <param name="workflow">The workflow being executed.</param>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <returns>A <see cref="DurableStreamingRun"/> that can be used to stream workflow events.</returns>
    public static DurableStreamingRun AttachStream(
        string instanceId,
        Workflow workflow,
        DurableTaskClient client)
    {
        ArgumentException.ThrowIfNullOrEmpty(instanceId);
        ArgumentNullException.ThrowIfNull(workflow);
        ArgumentNullException.ThrowIfNull(client);

        return new DurableStreamingRun(client, instanceId, workflow);
    }
}
