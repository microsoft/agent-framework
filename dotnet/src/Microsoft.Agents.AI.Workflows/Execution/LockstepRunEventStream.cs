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
    private static readonly string s_namespace = typeof(LockstepRunEventStream).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation = default) => new(this.RunStatus);

    public LockstepRunEventStream(ISuperStepRunner stepRunner)
    {
        this.StepRunner = stepRunner;
    }

    private RunStatus RunStatus { get; set; } = RunStatus.NotStarted;
    private ISuperStepRunner StepRunner { get; }

    public void Start()
    {
        // No-op for lockstep execution
    }

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync([EnumeratorCancellation] CancellationToken cancellation = default)
    {
        ConcurrentQueue<WorkflowEvent> eventSink = [];

        this.StepRunner.OutgoingEvents.EventRaised += OnWorkflowEventAsync;

        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowRun);
        activity?.SetTag(Tags.WorkflowId, this.StepRunner.StartExecutorId).SetTag(Tags.RunId, this.StepRunner.RunId);

        try
        {
            this.RunStatus = RunStatus.Running;
            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowStarted));

            do
            {
                // Because we may be yielding out of this function, we need to ensure that the Activity.Current
                // is set to our activity for the duration of this loop iteration.
                Activity.Current = activity;

                // Drain SuperSteps while there are steps to run
                try
                {
                    await this.StepRunner.RunSuperStepAsync(cancellation).ConfigureAwait(false);
                }
                catch (Exception ex) when (activity is not null)
                {
                    activity.AddEvent(new ActivityEvent(EventNames.WorkflowError, tags: new() {
                         { Tags.ErrorType, ex.GetType().FullName },
                         { Tags.BuildErrorMessage, ex.Message },
                    }));
                    activity.CaptureException(ex);
                    throw;
                }

                if (cancellation.IsCancellationRequested)
                {
                    yield break; // Exit if cancellation is requested
                }

                bool hadRequestHaltEvent = false;
                foreach (WorkflowEvent raisedEvent in Interlocked.Exchange(ref eventSink, []))
                {
                    if (cancellation.IsCancellationRequested)
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

                if (hadRequestHaltEvent)
                {
                    // If we had a completion event, we are done.
                    yield break;
                }
            } while (this.StepRunner.HasUnprocessedMessages &&
                     !cancellation.IsCancellationRequested);

            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowCompleted));
        }
        finally
        {
            this.RunStatus = this.StepRunner.HasUnservicedRequests ? RunStatus.PendingRequests : RunStatus.Idle;
            this.StepRunner.OutgoingEvents.EventRaised -= OnWorkflowEventAsync;
        }

        ValueTask OnWorkflowEventAsync(object? sender, WorkflowEvent e)
        {
            eventSink.Enqueue(e);
            return default;
        }
    }

    public ValueTask DisposeAsync() => default;
}
