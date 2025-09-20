// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Specifies the current operational state of a workflow run.
/// </summary>
public enum RunStatus
{
    /// <summary>
    /// The run has halted, has no outstanding requets, but has not received a <see cref="WorkflowCompletedEvent"/>.
    /// </summary>
    Idle,

    /// <summary>
    /// The run has halted, and has at least one outstanding <see cref="ExternalRequest"/>.
    /// </summary>
    PendingRequests,

    /// <summary>
    /// The run has halted after receiving a <see cref="WorkflowCompletedEvent"/>.
    /// </summary>
    Completed,

    /// <summary>
    /// The workflow is currently running, and may receive events or requests.
    /// </summary>
    Running
}

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events, supporting resumption
/// with responses to <see cref="RequestInfoEvent"/>.
/// </summary>
public class Run
{
    internal static async ValueTask<Run> CaptureStreamAsync(StreamingRun run, CancellationToken cancellation = default)
    {
        Run result = new(run);
        await result.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
        return result;
    }

    private readonly List<WorkflowEvent> _eventSink = [];
    private readonly StreamingRun _streamingRun;
    internal Run(StreamingRun streamingRun)
    {
        this._streamingRun = streamingRun;
    }

    internal async ValueTask<bool> RunToNextHaltAsync(CancellationToken cancellation = default)
    {
        bool hadEvents = false;
        bool hadCompletion = false;
        this.Status = RunStatus.Running;
        await foreach (WorkflowEvent evt in this._streamingRun.WatchStreamAsync(blockOnPendingRequest: false, cancellation).ConfigureAwait(false))
        {
            hadEvents = true;
            if (evt is WorkflowCompletedEvent)
            {
                hadCompletion = true;
            }

            this._eventSink.Add(evt);
        }

        // TODO: bookmark every halt for history visualization?

        this.Status =
            hadCompletion
            ? RunStatus.Completed
            : this._streamingRun.HasUnservicedRequests
              ? RunStatus.PendingRequests
              : RunStatus.Idle;

        return hadEvents;
    }

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
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the workflow execution.</param>
    /// <param name="responses">An array of <see cref="ExternalResponse"/> objects to send to the workflow.</param>
    /// <returns><c>true</c> if the workflow had any output events, <c>false</c> otherwise.</returns>
    public async ValueTask<bool> ResumeAsync(CancellationToken cancellation = default, params ExternalResponse[] responses)
    {
        foreach (ExternalResponse response in responses)
        {
            await this._streamingRun.SendResponseAsync(response).ConfigureAwait(false);
        }

        return await this.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
    }

    /// <summary>
    /// Resume execution of the workflow with the provided external responses.
    /// </summary>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the workflow execution.</param>
    /// <param name="messages">An array of messages to send to the workflow. Messages will only be sent if they are valid
    /// input types to the starting executor or a <see cref="ExternalResponse"/>.</param>
    /// <returns><c>true</c> if the workflow had any output events, <c>false</c> otherwise.</returns>
    public async ValueTask<bool> ResumeAsync<T>(CancellationToken cancellation = default, params T[] messages)
    {
        if (messages is ExternalResponse[] responses)
        {
            return await this.ResumeAsync(cancellation, responses).ConfigureAwait(false);
        }

        foreach (T message in messages)
        {
            await this._streamingRun.TrySendMessageAsync(message).ConfigureAwait(false);
        }

        return await this.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
    }
}

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events, supporting resumption
/// with responses to <see cref="RequestInfoEvent"/>, and retrieval of the running output of the workflow.
/// </summary>
/// <typeparam name="TResult">The type of the workflow output.</typeparam>
public sealed class Run<TResult> : Run
{
    internal static async ValueTask<Run<TResult>> CaptureStreamAsync(StreamingRun<TResult> run, CancellationToken cancellation = default)
    {
        Run<TResult> result = new(run);
        await result.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
        return result;
    }

    private readonly StreamingRun<TResult> _streamingRun;
    private Run(StreamingRun<TResult> streamingRun) : base(streamingRun)
    {
        this._streamingRun = streamingRun;
    }

    /// <inheritdoc cref="StreamingRun{TOutput}.RunningOutput"/>
    public TResult? RunningOutput => this._streamingRun.RunningOutput;
}
