// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Specifies the current operational state of a workflow run.
/// </summary>
public enum RunStatus
{
    /// <summary>
    /// The run has halted, has no outstanding requets, but has not received a <see cref="RequestHaltEvent"/>.
    /// </summary>
    Idle,

    /// <summary>
    /// The run has halted, and has at least one outstanding <see cref="ExternalRequest"/>.
    /// </summary>
    PendingRequests,

    // TODO: Figure out if we want to have some way to have a true "converged" state
    ///// <summary>
    ///// The run has halted after converging.
    ///// </summary>
    //Completed,

    /// <summary>
    /// The workflow is currently running, and may receive events or requests.
    /// </summary>
    Running
}

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events, supporting resumption
/// with responses to <see cref="RequestInfoEvent"/>.
/// </summary>
public sealed class Run
{
    internal static async ValueTask<Run> CaptureStreamAsync(StreamingRun run, CancellationToken cancellationToken = default)
    {
        Run result = new(run);
        await result.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return result;
    }

    private readonly List<WorkflowEvent> _eventSink = [];
    private readonly StreamingRun _streamingRun;
    internal Run(StreamingRun streamingRun)
    {
        this._streamingRun = streamingRun;
    }

    internal async ValueTask<bool> RunToNextHaltAsync(CancellationToken cancellationToken = default)
    {
        bool hadEvents = false;
        this.Status = RunStatus.Running;
        await foreach (WorkflowEvent evt in this._streamingRun.WatchStreamAsync(blockOnPendingRequest: false, cancellationToken).ConfigureAwait(false))
        {
            hadEvents = true;
            this._eventSink.Add(evt);
        }

        // TODO: bookmark every halt for history visualization?

        this.Status =
            this._streamingRun.HasUnservicedRequests
              ? RunStatus.PendingRequests
              : RunStatus.Idle;

        return hadEvents;
    }

    /// <summary>
    /// A unique identifier for the run. Can be provided at the start of the run, or auto-generated.
    /// </summary>
    public string RunId => this._streamingRun.RunId;

    /// <summary>
    /// Gets the current execution status of the workflow run.
    /// </summary>
    public RunStatus Status { get; private set; }

    /// <summary>
    /// Gets all events emitted by the workflow.
    /// </summary>
    public IEnumerable<WorkflowEvent> OutgoingEvents => this._eventSink;

    private int _lastBookmark;

    /// <summary>
    /// Gets all events emitted by the workflow since the last access to <see cref="NewEvents" />.
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
    /// Resume execution of the workflow with the provided external responses.
    /// </summary>
    /// <param name="responses">An array of <see cref="ExternalResponse"/> objects to send to the workflow.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns><c>true</c> if the workflow had any output events, <c>false</c> otherwise.</returns>
    public async ValueTask<bool> ResumeAsync(IEnumerable<ExternalResponse> responses, CancellationToken cancellationToken = default)
    {
        foreach (ExternalResponse response in responses)
        {
            await this._streamingRun.SendResponseAsync(response).ConfigureAwait(false);
        }

        return await this.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Resume execution of the workflow with the provided external responses.
    /// </summary>
    /// <param name="messages">An array of messages to send to the workflow. Messages will only be sent if they are valid
    /// input types to the starting executor or a <see cref="ExternalResponse"/>.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns><c>true</c> if the workflow had any output events, <c>false</c> otherwise.</returns>
    public async ValueTask<bool> ResumeAsync<T>(IEnumerable<T> messages, CancellationToken cancellationToken = default)
    {
        if (messages is IEnumerable<ExternalResponse> responses)
        {
            return await this.ResumeAsync(responses, cancellationToken).ConfigureAwait(false);
        }

        foreach (T message in messages)
        {
            await this._streamingRun.TrySendMessageAsync(message).ConfigureAwait(false);
        }

        return await this.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc cref="StreamingRun.EndRunAsync"/>
    public ValueTask EndRunAsync() => this._streamingRun.EndRunAsync();
}
