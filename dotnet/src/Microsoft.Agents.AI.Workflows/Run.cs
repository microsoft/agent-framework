// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events, supporting resumption
/// with responses to <see cref="RequestInfoEvent"/>.
/// </summary>
public sealed class Run : IAsyncDisposable
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
        await foreach (WorkflowEvent evt in this._runHandle.TakeEventStreamAsync(blockOnPendingRequest: false, cancellationToken).ConfigureAwait(false))
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
    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
        => this._runHandle.GetStatusAsync(cancellationToken);

    /// <summary>
    /// Gets all events emitted by the workflow.
    /// </summary>
    public IEnumerable<WorkflowEvent> OutgoingEvents => this._eventSink;

    private int _lastBookmark;

    /// <summary>
    /// The number of events emitted by the workflow since the last access to <see cref="NewEvents"/>
    /// </summary>
    public int NewEventCount => this._eventSink.Count - this._lastBookmark;

    /// <summary>
    /// Gets all events emitted by the workflow since the last access to <see cref="NewEvents" />.
    /// </summary>
    [DebuggerDisplay("NewEvents[{NewEventCount}]")]
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
                await this._runHandle.EnqueueMessageUntypedAsync(message, cancellationToken: cancellationToken).ConfigureAwait(false);
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

    /// <inheritdoc/>
    public ValueTask DisposeAsync()
    {
        return this._runHandle.DisposeAsync();
    }
}
