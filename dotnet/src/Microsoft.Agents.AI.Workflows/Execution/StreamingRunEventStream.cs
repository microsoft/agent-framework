// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

/// <summary>
/// A modern implementation of IRunEventStream that streams events as they are created,
/// using System.Threading.Channels for thread-safe coordination.
/// </summary>
internal sealed class StreamingRunEventStream : IRunEventStream
{
    private static readonly string s_namespace = typeof(StreamingRunEventStream).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

    private readonly Channel<WorkflowEvent> _eventChannel;
    private readonly ISuperStepRunner _stepRunner;
    private readonly InputWaiter _inputWaiter;
    private readonly CancellationTokenSource _runLoopCancellation;
    private readonly bool _disableRunLoop;
    private Task? _runLoopTask;
    private RunStatus _runStatus = RunStatus.NotStarted;
    private int _completionEpoch; // Tracks which completion signal belongs to which consumer iteration

    public StreamingRunEventStream(ISuperStepRunner stepRunner, bool disableRunLoop = false)
    {
        this._stepRunner = stepRunner;
        this._runLoopCancellation = new CancellationTokenSource();
        this._inputWaiter = new();
        this._disableRunLoop = disableRunLoop;

        // Unbounded channel - events never block the producer
        // This allows events to flow freely during superstep execution
        this._eventChannel = Channel.CreateUnbounded<WorkflowEvent>(new UnboundedChannelOptions
        {
            SingleReader = true,  // Only one consumer at a time (enforced by AsyncRunHandle)
            SingleWriter = false, // Events can come from multiple threads during superstep execution
            AllowSynchronousContinuations = false // Prevent potential deadlocks
        });
    }

    public void Start()
    {
        // Start the background run loop that drives superstep execution
        if (!this._disableRunLoop)
        {
            this._runLoopTask = Task.Run(() => this.RunLoopAsync(this._runLoopCancellation.Token));
        }
    }

    private async Task RunLoopAsync(CancellationToken cancellationToken)
    {
        using CancellationTokenSource errorSource = new();
        CancellationTokenSource linkedSource = CancellationTokenSource.CreateLinkedTokenSource(errorSource.Token, cancellationToken);

        // Subscribe to events - they will flow directly to the channel as they're raised
        this._stepRunner.OutgoingEvents.EventRaised += OnEventRaisedAsync;

        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowRun);
        activity?.SetTag(Tags.WorkflowId, this._stepRunner.StartExecutorId).SetTag(Tags.RunId, this._stepRunner.RunId);

        try
        {
            // Wait for the first input before starting
            // The consumer will call EnqueueMessageAsync which signals the run loop
            await this._inputWaiter.WaitForInputAsync(cancellationToken: linkedSource.Token).ConfigureAwait(false);

            this._runStatus = RunStatus.Running;
            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowStarted));

            while (!linkedSource.Token.IsCancellationRequested)
            {
                // Run all available supersteps continuously
                // Events are streamed out in real-time as they happen via the event handler
                while (this._stepRunner.HasUnprocessedMessages && !linkedSource.Token.IsCancellationRequested)
                {
                    await this._stepRunner.RunSuperStepAsync(linkedSource.Token).ConfigureAwait(false);
                }

                // Update status based on what's waiting
                this._runStatus = this._stepRunner.HasUnservicedRequests
                    ? RunStatus.PendingRequests
                    : RunStatus.Idle;

                // Signal completion to consumer so they can check status and decide whether to continue
                // Increment epoch so next consumer iteration gets a new completion signal
                // Capture the status at this moment to avoid race conditions with event reading
                int currentEpoch = Interlocked.Increment(ref this._completionEpoch);
                RunStatus capturedStatus = this._runStatus;
                await this._eventChannel.Writer.WriteAsync(new InternalHaltSignal(currentEpoch, capturedStatus), linkedSource.Token).ConfigureAwait(false);

                // Wait for next input from the consumer
                // Works for both Idle (no work) and PendingRequests (waiting for responses)
                await this._inputWaiter.WaitForInputAsync(TimeSpan.FromSeconds(1), linkedSource.Token).ConfigureAwait(false);

                // When signaled, resume running
                this._runStatus = RunStatus.Running;
            }
        }
        catch (OperationCanceledException)
        {
            // Expected during shutdown
        }
        catch (Exception ex)
        {
            if (activity != null)
            {
                activity.AddEvent(new ActivityEvent(EventNames.WorkflowError, tags: new() {
                             { Tags.ErrorType, ex.GetType().FullName },
                             { Tags.BuildErrorMessage, ex.Message },
                        }));
                activity.CaptureException(ex);
            }
            await this._eventChannel.Writer.WriteAsync(new WorkflowErrorEvent(ex), linkedSource.Token).ConfigureAwait(false);
        }
        finally
        {
            this._stepRunner.OutgoingEvents.EventRaised -= OnEventRaisedAsync;
            this._eventChannel.Writer.Complete();

            // Mark as ended when run loop exits
            this._runStatus = RunStatus.Ended;
            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowCompleted));
        }

        async ValueTask OnEventRaisedAsync(object? sender, WorkflowEvent e)
        {
            // Write event directly to channel - it's thread-safe and non-blocking
            // The channel handles all synchronization internally using lock-free algorithms
            // Events flow immediately to consumers rather than being batched
            await this._eventChannel.Writer.WriteAsync(e, linkedSource.Token).ConfigureAwait(false);

            if (e is WorkflowErrorEvent error)
            {
                errorSource.Cancel();
            }
        }
    }

    /// <summary>
    /// Signals that new input has been provided and the run loop should continue processing.
    /// Called by AsyncRunHandle when the user enqueues a message or response.
    /// </summary>
    public void SignalInput() => this._inputWaiter.SignalInput();

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync(
        bool blockOnPendingRequest,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Get the current epoch - we'll only respond to completion signals from this epoch or later
        int myEpoch = Volatile.Read(ref this._completionEpoch) + 1;

        // Use custom async enumerable to avoid exceptions on cancellation.
        NonThrowingChannelReaderAsyncEnumerable<WorkflowEvent> eventStream = new(this._eventChannel.Reader);
        await foreach (WorkflowEvent evt in eventStream.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            // Filter out internal signals used for run loop coordination
            if (evt is InternalHaltSignal completionSignal)
            {
                // Ignore completion signals from previous iterations
                if (completionSignal.Epoch < myEpoch)
                {
                    continue;
                }

                // Check for cancellation at superstep boundaries (before processing completion signal)
                // This allows consumers to stop reading events cleanly between supersteps
                if (cancellationToken.IsCancellationRequested)
                {
                    yield break;
                }

                // Check if we should stop streaming based on the status captured at completion time
                // This avoids race conditions where _runStatus changes while events are being read
                // - Idle: Workflow completed, no pending requests
                // - Ended: Run loop disposed/cancelled
                // Note: PendingRequests is handled by WatchStreamAsync's do-while loop
                if (completionSignal.Status is RunStatus.Idle or RunStatus.Ended)
                {
                    yield break;
                }

                if (!blockOnPendingRequest && completionSignal.Status is RunStatus.PendingRequests)
                {
                    yield break;
                }

                // Otherwise continue reading (more events coming after input provided)
                continue;
            }

            // RequestHaltEvent signals the end of the event stream
            if (evt is RequestHaltEvent)
            {
                yield break;
            }

            if (cancellationToken.IsCancellationRequested)
            {
                yield break;
            }

            yield return evt;
        }
    }

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
    {
        // Thread-safe read of status (enum is read atomically on most platforms)
        return new ValueTask<RunStatus>(this._runStatus);
    }

    /// <summary>
    /// Clears all buffered events from the channel.
    /// This should be called when restoring a checkpoint to discard stale events from superseded supersteps.
    /// </summary>
    public void ClearBufferedEvents()
    {
        // Drain all events currently in the channel buffer
        // We discard all events since they're from a timeline that's been superseded by the checkpoint restore
        while (this._eventChannel.Reader.TryRead(out _))
        {
            // Discard each event (including InternalCompletionSignals)
        }

        // After clearing, signal the run loop to continue if needed
        // The run loop will send a new completion signal when it finishes processing from the restored state
        this.SignalInput();
    }

    public async ValueTask StopAsync()
    {
        // Cancel the run loop
        this._runLoopCancellation.Cancel();

        // Release the event waiter, if any
        this._inputWaiter.SignalInput();

        // Wait for clean shutdown
        if (this._runLoopTask != null)
        {
            try
            {
                await this._runLoopTask.ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                // Expected during cancellation
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        await this.StopAsync().ConfigureAwait(false);

        // Dispose resources
        this._runLoopCancellation.Dispose();
        this._inputWaiter.Dispose();
    }

    /// <summary>
    /// Internal signal used to mark completion of a work batch and allow status checking.
    /// This is never exposed to consumers.
    /// </summary>
    private sealed class InternalHaltSignal(int epoch, RunStatus status) : WorkflowEvent
    {
        public int Epoch => epoch;
        public RunStatus Status => status;
    }
}
