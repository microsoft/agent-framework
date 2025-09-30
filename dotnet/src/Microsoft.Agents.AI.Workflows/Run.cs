// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Specifies the current operational state of a workflow run.
/// </summary>
public enum RunStatus
{
    /// <summary>
    /// The run has not yet started. This only occurs when running in "lockstep" mode.
    /// </summary>
    NotStarted,

    /// <summary>
    /// The run has halted, has no outstanding requets, but has not received a <see cref="RequestHaltEvent"/>.
    /// </summary>
    Idle,

    /// <summary>
    /// The run has halted, and has at least one outstanding <see cref="ExternalRequest"/>.
    /// </summary>
    PendingRequests,

    /// <summary>
    /// The user has ended the run. No further events will be emitted, and no messages can be sent to it.
    /// </summary>
    /// <seealso cref="StreamingRun.EndRunAsync"/>
    /// <seealso cref="Run.EndRunAsync"/>
    Ended,

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
    private readonly List<WorkflowEvent> _eventSink = [];
    private readonly AsyncRunHandle _runHandle;
    internal Run(AsyncRunHandle _runHandle)
    {
        this._runHandle = _runHandle;
    }

    internal async ValueTask<bool> RunToNextHaltAsync(CancellationToken cancellationToken = default)
    {
        bool hadEvents = false;
        await foreach (WorkflowEvent evt in this._runHandle.TakeEventStreamAsync(breakOnHalt: true, cancellationToken).ConfigureAwait(false))
        {
            hadEvents = true;
            this._eventSink.Add(evt);
        }

        return hadEvents;
    }

    /// <summary>
    /// A unique identifier for the run. Can be provided at the start of the run, or auto-generated.
    /// </summary>
    public string RunId => this._runHandle.RunId;

    /// <summary>
    /// Gets the current execution status of the workflow run.
    /// </summary>
    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation = default)
        => this._runHandle.GetStatusAsync(cancellation);

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
            await this._runHandle.EnqueueResponseAsync(response, cancellationToken).ConfigureAwait(false);
        }

        return await this.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Resume execution of the workflow with the provided external responses.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <param name="messages">An array of messages to send to the workflow. Messages will only be sent if they are valid
    /// input types to the starting executor or a <see cref="ExternalResponse"/>.</param>
    /// <returns><c>true</c> if the workflow had any output events, <c>false</c> otherwise.</returns>
    public async ValueTask<bool> ResumeAsync<T>(CancellationToken cancellationToken = default, params IEnumerable<T> messages)
        where T : notnull
    {
        if (messages is IEnumerable<ExternalResponse> responses)
        {
            return await this.ResumeAsync(responses, cancellationToken).ConfigureAwait(false);
        }

        if (typeof(T) == typeof(object))
        {
            foreach (object? message in messages)
            {
                await this._runHandle.EnqueueMessageUntypedAsync(message, cancellation: cancellationToken).ConfigureAwait(false);
            }
        }
        else
        {
            foreach (T message in messages)
            {
                await this._runHandle.EnqueueMessageAsync(message, cancellationToken).ConfigureAwait(false);
            }
        }

        return await this.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc cref="StreamingRun.EndRunAsync"/>
    public ValueTask EndRunAsync() => this._runHandle.RequestEndRunAsync();
}
