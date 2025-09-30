// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal class OffThreadRunEventStream : IRunEventStream
{
    private static readonly string s_namespace = typeof(OffThreadRunEventStream).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

    private class OffThreadHaltSignal(int epoch) : WorkflowEvent
    {
        public int Epoch => epoch;
    }

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation = default) => new(this.RunStatus);

    public RunStatus RunStatus { get; private set; } = RunStatus.NotStarted;

    private readonly IInputCoordinator _inputCoordinator;
    private readonly AsyncCoordinator _outputCoordinator = new();

    private readonly CancellationTokenSource _endRunSource = new();
    private readonly InitLocked<Task> _runLoopTask = new();
    private readonly InitLocked<Task> _disposeTask = new();

    private int _isTaken;
    private int _streamEpoch;

    private readonly ConcurrentQueue<WorkflowEvent> _eventSink = new();

    public OffThreadRunEventStream(ISuperStepRunner stepRunner, IInputCoordinator inputCoordinator)
    {
        this.StepRunner = stepRunner;

        this._inputCoordinator = inputCoordinator;
    }

    private ISuperStepRunner StepRunner { get; }

    public void Start()
    {
        this._runLoopTask.Init(() => Task.Run(() => this.RunLoopAsync(), this._endRunSource.Token));
    }

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync([EnumeratorCancellation] CancellationToken cancellation = default)
    {
        try
        {
            if (Interlocked.Exchange(ref this._isTaken, 1) != 0)
            {
                throw new InvalidOperationException("Can only have one active watcher on the event stream at a time.");
            }

            while (!cancellation.IsCancellationRequested)
            {
                if (this._eventSink.TryDequeue(out WorkflowEvent? @event) &&
                    !cancellation.IsCancellationRequested)
                {
                    if (@event is OffThreadHaltSignal haltSignal)
                    {
                        int runningEpoch = Volatile.Read(ref this._streamEpoch);
                        if (haltSignal.Epoch >= runningEpoch)
                        {
                            // We hit a halt signal for our current epoch, so we are done.
                            yield break;
                        }

                        // We hit a halt signal for a previous epoch, so we ignore it.
                    }
                    else
                    {
                        yield return @event;
                    }
                }
                else if (!cancellation.IsCancellationRequested)
                {
                    await this._outputCoordinator.WaitForCoordinationAsync(cancellation).ConfigureAwait(false);
                }
            }
        }
        finally
        {
            Volatile.Write(ref this._isTaken, 0);
        }
    }

    private void NotifyHalt()
    {
        int epoch = Math.Max(Volatile.Read(ref this._streamEpoch), 0);
        this._eventSink.Enqueue(new OffThreadHaltSignal(epoch));
    }

    private async Task RunLoopAsync(CancellationToken cancellation = default)
    {
        this.StepRunner.OutgoingEvents.EventRaised += InspectAndForwardWorkflowEventAsync;
        bool hadRequestHaltEvent = false;

        int epoch = Volatile.Read(ref this._streamEpoch);

        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowRun);
        activity?.SetTag(Tags.WorkflowId, this.StepRunner.StartExecutorId).SetTag(Tags.RunId, this.StepRunner.RunId);

        try
        {
            while (!cancellation.IsCancellationRequested && !hadRequestHaltEvent)
            {
                this.RunStatus = RunStatus.Running;
                activity?.AddEvent(new ActivityEvent(EventNames.WorkflowStarted));

                do
                {
                    // TODO: Needed?
                    // Because we may be yielding out of this function, we need to ensure that the Activity.Current
                    // is set to our activity for the duration of this loop iteration.
                    // Activity.Current = activity;

                    bool hadActions = await this.StepRunner.RunSuperStepAsync(cancellation).ConfigureAwait(false);
                } while (this.StepRunner.HasUnprocessedMessages &&
                         !hadRequestHaltEvent &&
                         !cancellation.IsCancellationRequested);

                this.RunStatus = this.StepRunner.HasUnservicedRequests ? RunStatus.PendingRequests : RunStatus.Idle;

                this.NotifyHalt();
                this._outputCoordinator.MarkCoordinationPoint();

                // Ideally, these would happen atomically.
                await this._inputCoordinator.WaitForNextInputAsync(cancellation).ConfigureAwait(false);
                epoch = Interlocked.Increment(ref this._streamEpoch);
            }

            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowCompleted));
        }
        finally
        {
            this.StepRunner.OutgoingEvents.EventRaised -= InspectAndForwardWorkflowEventAsync;
        }

        [SuppressMessage("Usage", "VSTHRD100:Avoid async void methods", Justification = "Internal event handler - nowhere to return exceptions to.")]
        async ValueTask InspectAndForwardWorkflowEventAsync(object? sender, WorkflowEvent e)
        {
            int epoch = Volatile.Read(ref this._streamEpoch);
            if (e is RequestHaltEvent)
            {
                hadRequestHaltEvent = true;
                this.NotifyHalt();
            }
            else
            {
                this._eventSink.Enqueue(e);
            }

            this._outputCoordinator.MarkCoordinationPoint();
        }
    }

    private async Task DisposeCoreAsync()
    {
        this._endRunSource.Cancel();
        this._endRunSource.Dispose();

        this.NotifyHalt();
        this._outputCoordinator.MarkCoordinationPoint();

        try
        {
            // Wait for the cancellation to propagate
            Task? loopTask = this._runLoopTask.Get();

            if (loopTask != null)
            {
                await loopTask.ConfigureAwait(false);
            }
        }
        catch { }
    }

    public async ValueTask DisposeAsync()
    {
        this._disposeTask.Init(this.DisposeCoreAsync);
        await this._disposeTask.Get()!.ConfigureAwait(false);
    }
}
