// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a durable workflow run that tracks execution status and provides access to workflow events.
/// </summary>
/// <remarks>
/// This class provides a similar API to <see cref="Run"/> but for workflows executed as durable orchestrations.
/// Events are received by raising external events to the orchestration and can be streamed to the caller.
/// </remarks>
public sealed class DurableRun : IAsyncDisposable
{
    private readonly DurableTaskClient _client;
    private readonly List<WorkflowEvent> _eventSink = [];
    private int _lastBookmark;

    internal DurableRun(DurableTaskClient client, string instanceId, string workflowName)
    {
        this._client = client;
        this.InstanceId = instanceId;
        this.WorkflowName = workflowName;
    }

    /// <summary>
    /// Gets the unique instance ID for this orchestration run.
    /// </summary>
    public string InstanceId { get; }

    /// <summary>
    /// Gets the name of the workflow being executed.
    /// </summary>
    public string WorkflowName { get; }

    /// <summary>
    /// Gets the current execution status of the workflow run.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The current status of the durable run.</returns>
    public async ValueTask<DurableRunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
    {
        OrchestrationMetadata? metadata = await this._client.GetInstanceAsync(
            this.InstanceId,
            getInputsAndOutputs: false,
            cancellation: cancellationToken).ConfigureAwait(false);

        if (metadata is null)
        {
            return DurableRunStatus.NotFound;
        }

        return metadata.RuntimeStatus switch
        {
            OrchestrationRuntimeStatus.Pending => DurableRunStatus.Pending,
            OrchestrationRuntimeStatus.Running => DurableRunStatus.Running,
            OrchestrationRuntimeStatus.Completed => DurableRunStatus.Completed,
            OrchestrationRuntimeStatus.Failed => DurableRunStatus.Failed,
            OrchestrationRuntimeStatus.Terminated => DurableRunStatus.Terminated,
            OrchestrationRuntimeStatus.Suspended => DurableRunStatus.Suspended,
            _ => DurableRunStatus.Unknown
        };
    }

    /// <summary>
    /// Waits for the workflow to complete and returns the result.
    /// </summary>
    /// <typeparam name="TResult">The expected result type.</typeparam>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The result of the workflow execution.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the workflow failed or was terminated.</exception>
    public async ValueTask<TResult?> WaitForCompletionAsync<TResult>(CancellationToken cancellationToken = default)
    {
        OrchestrationMetadata metadata = await this._client.WaitForInstanceCompletionAsync(
            this.InstanceId,
            getInputsAndOutputs: true,
            cancellation: cancellationToken).ConfigureAwait(false);

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
        {
            return metadata.ReadOutputAs<TResult>();
        }

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
        {
            string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Workflow execution failed.";
            throw new InvalidOperationException(errorMessage);
        }

        throw new InvalidOperationException($"Workflow ended with unexpected status: {metadata.RuntimeStatus}");
    }

    /// <summary>
    /// Waits for the workflow to complete and returns the string result.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The string result of the workflow execution.</returns>
    public ValueTask<string?> WaitForCompletionAsync(CancellationToken cancellationToken = default)
        => this.WaitForCompletionAsync<string>(cancellationToken);

    /// <summary>
    /// Sends an external event to the workflow orchestration.
    /// </summary>
    /// <remarks>
    /// This can be used to send responses or messages to the workflow while it's running.
    /// The orchestration must be waiting for the event using <c>WaitForExternalEvent</c>.
    /// </remarks>
    /// <param name="eventName">The name of the event to raise.</param>
    /// <param name="eventData">The data to send with the event.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
#pragma warning disable CA1030 // Use events where appropriate - This is intentionally a method that sends events to an orchestration
    public async ValueTask SendExternalEventAsync(string eventName, object? eventData = null, CancellationToken cancellationToken = default)
#pragma warning restore CA1030
    {
        await this._client.RaiseEventAsync(
            this.InstanceId,
            eventName,
            eventData,
            cancellation: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Sends a workflow event to the orchestration.
    /// </summary>
    /// <param name="workflowEvent">The workflow event to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    public ValueTask SendEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
        => this.SendExternalEventAsync("WorkflowEvent", workflowEvent, cancellationToken);

    /// <summary>
    /// Sends an external response to the workflow.
    /// </summary>
    /// <param name="response">The external response to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    public ValueTask SendResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default)
        => this.SendExternalEventAsync("ExternalResponse", response, cancellationToken);

    /// <summary>
    /// Sends a response to a pending request port in the workflow (human-in-the-loop).
    /// </summary>
    /// <remarks>
    /// The response is serialized to JSON before being sent to match what the orchestration expects.
    /// Use this method when responding to a <see cref="RequestPort"/> that is waiting for external input.
    /// </remarks>
    /// <typeparam name="TResponse">The type of the response data.</typeparam>
    /// <param name="requestPortId">The ID of the request port to respond to.</param>
    /// <param name="response">The response data to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types provided by the caller.")]
    public ValueTask SendResponseAsync<TResponse>(string requestPortId, TResponse response, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(requestPortId);

        // Serialize the response to JSON string - the orchestration expects a string via WaitForExternalEvent<string>
        string serializedResponse = JsonSerializer.Serialize(response);
        return this.SendExternalEventAsync(requestPortId, serializedResponse, cancellationToken);
    }

    /// <summary>
    /// Gets all events that have been collected from the workflow.
    /// </summary>
    public IEnumerable<WorkflowEvent> OutgoingEvents => this._eventSink;

    /// <summary>
    /// Gets the number of events collected since the last access to <see cref="NewEvents"/>.
    /// </summary>
    public int NewEventCount => this._eventSink.Count - this._lastBookmark;

    /// <summary>
    /// Gets all events collected since the last access to <see cref="NewEvents"/>.
    /// </summary>
    public IEnumerable<WorkflowEvent> NewEvents
    {
        get
        {
            if (this._lastBookmark >= this._eventSink.Count)
            {
                return [];
            }

            int currentBookmark = this._lastBookmark;
            this._lastBookmark = this._eventSink.Count;

            return this._eventSink.Skip(currentBookmark);
        }
    }

    /// <summary>
    /// Adds an event to the local event sink.
    /// </summary>
    /// <remarks>
    /// This is used internally to collect events raised by the orchestration.
    /// In the durable scenario, events are typically returned as part of the orchestration output
    /// or raised via external events.
    /// </remarks>
    /// <param name="workflowEvent">The event to add.</param>
    internal void AddEvent(WorkflowEvent workflowEvent)
    {
        this._eventSink.Add(workflowEvent);
    }

    /// <summary>
    /// Terminates the workflow orchestration.
    /// </summary>
    /// <param name="reason">An optional reason for the termination.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    public async ValueTask TerminateAsync(string? reason = null, CancellationToken cancellationToken = default)
    {
        await this._client.TerminateInstanceAsync(
            this.InstanceId,
            reason,
            cancellation: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Purges the orchestration instance history.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    public async ValueTask PurgeAsync(CancellationToken cancellationToken = default)
    {
        await this._client.PurgeInstanceAsync(
            this.InstanceId,
            cancellation: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public ValueTask DisposeAsync()
    {
        // Nothing to dispose for durable runs - the orchestration continues independently
        return default;
    }
}

/// <summary>
/// Represents the execution status of a durable workflow run.
/// </summary>
public enum DurableRunStatus
{
    /// <summary>
    /// The orchestration instance was not found.
    /// </summary>
    NotFound,

    /// <summary>
    /// The orchestration is pending and has not started.
    /// </summary>
    Pending,

    /// <summary>
    /// The orchestration is currently running.
    /// </summary>
    Running,

    /// <summary>
    /// The orchestration completed successfully.
    /// </summary>
    Completed,

    /// <summary>
    /// The orchestration failed with an error.
    /// </summary>
    Failed,

    /// <summary>
    /// The orchestration was terminated.
    /// </summary>
    Terminated,

    /// <summary>
    /// The orchestration is suspended.
    /// </summary>
    Suspended,

    /// <summary>
    /// The orchestration status is unknown.
    /// </summary>
    Unknown
}
