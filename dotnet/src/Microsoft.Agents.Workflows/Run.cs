// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a workflow run that tracks execution status and emitted workflow events, supporting resumption
/// with responses to <see cref="RequestInfoEvent"/>.
/// </summary>
public class Run
{
    private readonly List<WorkflowEvent> _eventSink = new();
    private readonly IAsyncRunHandle _runHandle;
    internal Run(IAsyncRunHandle runHandle)
    {
        this._runHandle = runHandle;
    }

    internal async ValueTask<bool> RunToNextHaltAsync(CancellationToken cancellation = default)
    {
        bool hadEvents = false;
        this.Status = RunStatus.Running;

        await foreach (WorkflowEvent evt in this._runHandle.ForwardEventsAsync(breakOnHalt: true, cancellation).ConfigureAwait(false))
        {
            hadEvents = true;
            this._eventSink.Add(evt);
        }

        this.Status = await this._runHandle.GetStatusAsync(cancellation).ConfigureAwait(false);
        if (this.Status == RunStatus.Completed)
        {
            Debug.Assert(this._eventSink.Any(evt => evt is WorkflowCompletedEvent), "Run completed without a WorkflowCompletedEvent.");
        }

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

    private int _lastBookmark = 0;

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
            await this._runHandle.EnqueueResponseAsync(response).ConfigureAwait(false);
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
    public async ValueTask<bool> ResumeAsync<T>(CancellationToken cancellation = default, params T[] messages) where T : notnull
    {
        if (messages is ExternalResponse[] responses)
        {
            return await this.ResumeAsync(cancellation, responses).ConfigureAwait(false);
        }

        foreach (T message in messages)
        {
            await this._runHandle.EnqueueMessageAsync(message, cancellation).ConfigureAwait(false);
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
    private readonly IRunHandleWithOutput<TResult> _outputSource;
    internal Run(IRunHandleWithOutput<TResult> runHandleWithOutput) : base(runHandleWithOutput.RunHandle)
    {
        this._outputSource = runHandleWithOutput;
    }

    /// <summary>
    /// Retrieves the current output value if available, even if the operation has not yet completed.
    /// </summary>
    /// <param name="cancellation">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A ValueTask containing the current output value if available; otherwise, null if no output has been produced
    /// yet.</returns>
    public ValueTask<TResult?> GetRunningOutputAsync(CancellationToken cancellation = default)
        => this._outputSource.GetRunningOutputAsync(cancellation);
}
