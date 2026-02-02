// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a durable workflow run that tracks execution status and provides access to workflow events.
/// </summary>
[DebuggerDisplay("{WorkflowName} ({RunId})")]
internal sealed class DurableWorkflowRun : IAwaitableWorkflowRun
{
    private readonly DurableTaskClient _client;
    private readonly List<WorkflowEvent> _eventSink = [];
    private int _lastBookmark;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowRun"/> class.
    /// </summary>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">The unique instance ID for this orchestration run.</param>
    /// <param name="workflowName">The name of the workflow being executed.</param>
    internal DurableWorkflowRun(DurableTaskClient client, string instanceId, string workflowName)
    {
        this._client = client;
        this.RunId = instanceId;
        this.WorkflowName = workflowName;
    }

    /// <inheritdoc/>
    public string RunId { get; }

    /// <summary>
    /// Gets the name of the workflow being executed.
    /// </summary>
    public string WorkflowName { get; }

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
            this.RunId,
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
}
