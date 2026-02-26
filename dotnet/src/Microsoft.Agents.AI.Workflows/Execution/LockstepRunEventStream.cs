// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class LockstepRunEventStream : IRunEventStream
{
    private readonly CancellationTokenSource _stopCancellation = new();
    private readonly InputWaiter _inputWaiter = new();
    private int _isDisposed;

    private readonly ISuperStepRunner _stepRunner;
    private Activity? _sessionActivity;

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellationToken = default) => new(this.RunStatus);

    public LockstepRunEventStream(ISuperStepRunner stepRunner)
    {
        this._stepRunner = stepRunner;
    }

    private RunStatus RunStatus { get; set; } = RunStatus.NotStarted;

    public void Start()
    {
        // Save and restore Activity.Current so the long-lived session activity
        // doesn't leak into caller code via AsyncLocal.
        Activity? previousActivity = Activity.Current;

        this._sessionActivity = this._stepRunner.TelemetryContext.StartWorkflowSessionActivity();
        this._sessionActivity?.SetTag(Tags.WorkflowId, this._stepRunner.StartExecutorId)
                              .SetTag(Tags.SessionId, this._stepRunner.SessionId);
        this._sessionActivity?.AddEvent(new ActivityEvent(EventNames.SessionStarted));

        Activity.Current = previousActivity;
    }

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync(bool blockOnPendingRequest, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
#if NET
        ObjectDisposedException.ThrowIf(Volatile.Read(ref this._isDisposed) == 1, this);
#else
        if (Volatile.Read(ref this._isDisposed) == 1)
        {
            throw new ObjectDisposedException(nameof(LockstepRunEventStream));
        }
#endif

        using CancellationTokenSource linkedSource = CancellationTokenSource.CreateLinkedTokenSource(this._stopCancellation.Token, cancellationToken);

        ConcurrentQueue<WorkflowEvent> eventSink = [];

        this._stepRunner.OutgoingEvents.EventRaised += OnWorkflowEventAsync;

        // Re-establish session as parent so the run activity nests correctly.
        Activity.Current = this._sessionActivity;

        // Not 'using' — must dispose explicitly in finally for deterministic export.
        Activity? runActivity = this._stepRunner.TelemetryContext.StartWorkflowRunActivity();
        runActivity?.SetTag(Tags.WorkflowId, this._stepRunner.StartExecutorId).SetTag(Tags.SessionId, this._stepRunner.SessionId);

        try
        {
            this.RunStatus = RunStatus.Running;
            runActivity?.AddEvent(new ActivityEvent(EventNames.WorkflowStarted));

            do
            {
                while (this._stepRunner.HasUnprocessedMessages &&
                       !linkedSource.Token.IsCancellationRequested)
                {
                    // Because we may be yielding out of this function, we need to ensure that the Activity.Current
                    // is set to our activity for the duration of this loop iteration.
                    Activity.Current = runActivity;

                    // Drain SuperSteps while there are steps to run
                    try
                    {
                        await this._stepRunner.RunSuperStepAsync(linkedSource.Token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                    }
                    catch (Exception ex) when (runActivity is not null)
                    {
                        runActivity.AddEvent(new ActivityEvent(EventNames.WorkflowError, tags: new() {
                             { Tags.ErrorType, ex.GetType().FullName },
                             { Tags.ErrorMessage, ex.Message },
                        }));
                        runActivity.CaptureException(ex);
                        throw;
                    }

                    if (linkedSource.Token.IsCancellationRequested)
                    {
                        yield break; // Exit if cancellation is requested
                    }

                    bool hadRequestHaltEvent = false;
                    foreach (WorkflowEvent raisedEvent in Interlocked.Exchange(ref eventSink, []))
                    {
                        if (linkedSource.Token.IsCancellationRequested)
                        {
                            yield break; // Exit if cancellation is requested
                        }

                        // TODO: Do we actually want to interpret this as a termination request?
                        if (raisedEvent is RequestHaltEvent)
                        {
                            hadRequestHaltEvent = true;
                        }
                        else
                        {
                            yield return raisedEvent;
                        }
                    }

                    if (hadRequestHaltEvent || linkedSource.Token.IsCancellationRequested)
                    {
                        // If we had a completion event, we are done.
                        yield break;
                    }

                    this.RunStatus = this._stepRunner.HasUnservicedRequests ? RunStatus.PendingRequests : RunStatus.Idle;
                }

                if (blockOnPendingRequest && this.RunStatus == RunStatus.PendingRequests)
                {
                    try
                    {
                        await this._inputWaiter.WaitForInputAsync(TimeSpan.FromSeconds(1), linkedSource.Token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    { }
                }
            } while (!ShouldBreak());

            runActivity?.AddEvent(new ActivityEvent(EventNames.WorkflowCompleted));
        }
        finally
        {
            this.RunStatus = this._stepRunner.HasUnservicedRequests ? RunStatus.PendingRequests : RunStatus.Idle;
            this._stepRunner.OutgoingEvents.EventRaised -= OnWorkflowEventAsync;

            // Explicitly dispose the Activity so Activity.Stop fires deterministically,
            // regardless of how the async iterator enumerator is disposed.
            runActivity?.Dispose();
        }

        ValueTask OnWorkflowEventAsync(object? sender, WorkflowEvent e)
        {
            eventSink.Enqueue(e);
            return default;
        }

        // If we are Idle or Ended, we should break out of the loop
        // If we are PendingRequests and not blocking on pending requests, we should break out of the loop
        // If cancellation is requested, we should break out of the loop
        bool ShouldBreak() => this.RunStatus is RunStatus.Idle or RunStatus.Ended ||
                              (this.RunStatus == RunStatus.PendingRequests && !blockOnPendingRequest) ||
                              linkedSource.Token.IsCancellationRequested;
    }

    /// <summary>
    /// Signals that new input has been provided and the run loop should continue processing.
    /// Called by AsyncRunHandle when the user enqueues a message or response.
    /// </summary>
    public void SignalInput()
    {
        this._inputWaiter?.SignalInput();
    }

    public ValueTask StopAsync()
    {
        this._stopCancellation.Cancel();
        return default;
    }

    public ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref this._isDisposed, 1) == 0)
        {
            this._stopCancellation.Cancel();

            // Stop the session activity
            if (this._sessionActivity is not null)
            {
                this._sessionActivity.AddEvent(new ActivityEvent(EventNames.SessionCompleted));
                this._sessionActivity.Dispose();
                this._sessionActivity = null;
            }

            this._stopCancellation.Dispose();
            this._inputWaiter.Dispose();
        }

        return default;
    }
}
