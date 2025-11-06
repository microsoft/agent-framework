// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal delegate bool WorkflowEventHandler<in TEvent>(TEvent evt) where TEvent : WorkflowEvent;
internal delegate ValueTask<bool> WorkflowEventHandlerAsync<in TEvent>(TEvent evt) where TEvent : WorkflowEvent;

internal class StreamingRunWatcher
{
    private readonly ConcurrentDictionary<Type, IWorkflowEventChain> _eventHandlerChains = new();

    public StreamingRunWatcher()
    {
        this.SuperStepCompleted += evt =>
        {
            this.LastCheckpoint = evt.CompletionInfo?.Checkpoint;
            return false;
        };
    }

    public event WorkflowEventHandler<WorkflowStartedEvent> WorkflowStarted
    {
        add => this.For<WorkflowStartedEvent>().Event += value;
        remove => this.For<WorkflowStartedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<WorkflowErrorEvent> WorkflowError
    {
        add => this.For<WorkflowErrorEvent>().Event += value;
        remove => this.For<WorkflowErrorEvent>().Event -= value;
    }

    public event WorkflowEventHandler<WorkflowWarningEvent> WorkflowWarning
    {
        add => this.For<WorkflowWarningEvent>().Event += value;
        remove => this.For<WorkflowWarningEvent>().Event -= value;
    }

    public event WorkflowEventHandler<SuperStepStartedEvent> SuperStepStarted
    {
        add => this.For<SuperStepStartedEvent>().Event += value;
        remove => this.For<SuperStepStartedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<SuperStepCompletedEvent> SuperStepCompleted
    {
        add => this.For<SuperStepCompletedEvent>().Event += value;
        remove => this.For<SuperStepCompletedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<ExecutorInvokedEvent> ExecutorInvoked
    {
        add => this.For<ExecutorInvokedEvent>().Event += value;
        remove => this.For<ExecutorInvokedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<ExecutorFailedEvent> ExecutorFailed
    {
        add => this.For<ExecutorFailedEvent>().Event += value;
        remove => this.For<ExecutorFailedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<ExecutorCompletedEvent> ExecutorCompleted
    {
        add => this.For<ExecutorCompletedEvent>().Event += value;
        remove => this.For<ExecutorCompletedEvent>().Event -= value;
    }

    public event WorkflowEventHandler<AgentRunUpdateEvent> AgentRunUpdate
    {
        add => this.For<AgentRunUpdateEvent>().Event += value;
        remove => this.For<AgentRunUpdateEvent>().Event -= value;
    }

    public event WorkflowEventHandler<AgentRunResponseEvent> AgentRunResponse
    {
        add => this.For<AgentRunResponseEvent>().Event += value;
        remove => this.For<AgentRunResponseEvent>().Event -= value;
    }

    public event WorkflowEventHandler<RequestInfoEvent> RequestInfo
    {
        add => this.For<RequestInfoEvent>().Event += value;
        remove => this.For<RequestInfoEvent>().Event -= value;
    }

    public event WorkflowEventHandler<WorkflowOutputEvent> WorkflowOutput
    {
        add => this.For<WorkflowOutputEvent>().Event += value;
        remove => this.For<WorkflowOutputEvent>().Event -= value;
    }

    public event WorkflowEventHandler<SubworkflowErrorEvent> SubworkflowError
    {
        add => this.For<SubworkflowErrorEvent>().Event += value;
        remove => this.For<SubworkflowErrorEvent>().Event -= value;
    }

    public event WorkflowEventHandler<SubworkflowWarningEvent> SubworkflowWarning
    {
        add => this.For<SubworkflowWarningEvent>().Event += value;
        remove => this.For<SubworkflowWarningEvent>().Event -= value;
    }

    public EventBinding<TEvent> For<TEvent>() where TEvent : WorkflowEvent
    {
        IWorkflowEventChain chainObj = this._eventHandlerChains.GetOrAdd(typeof(TEvent), _ => new EventChain<TEvent>());
        Debug.Assert(chainObj is EventChain<TEvent>);
        EventChain<TEvent> eventChain = (EventChain<TEvent>)chainObj;

        return new(eventChain);
    }

    public async ValueTask RunToHaltAsync(StreamingRun streamingRun, CancellationToken cancellationToken = default)
    {
        List<RequestInfoEvent> pendingRequestInfoEvents = new();

        // TODO: Should we make some kind of facility to make it easier to shunt events to run on the "UI" / "main" thread?
        await foreach (WorkflowEvent evt in streamingRun.WatchStreamAsync(cancellationToken)
                                                        .WithCancellation(cancellationToken)
                                                        .ConfigureAwait(false))
        {
            if (evt is RequestInfoEvent requestInfoEvt)
            {
                pendingRequestInfoEvents.Add(requestInfoEvt);
                continue;
            }

            await TryInvokeHandlerAsync(evt).ConfigureAwait(false);

            if (evt is SuperStepCompletedEvent)
            {
                foreach (RequestInfoEvent pendingEvt in pendingRequestInfoEvents)
                {
                    await TryInvokeHandlerAsync(pendingEvt).ConfigureAwait(false);
                }

                pendingRequestInfoEvents.Clear();
            }
        }

        async ValueTask TryInvokeHandlerAsync(WorkflowEvent evt)
        {
            Type? eventType = evt.GetType();
            bool handled = false;

            while (!handled && eventType != null)
            {
                // Check if there are any handlers for this event type, and see if they handle the event.
                if (this._eventHandlerChains.TryGetValue(evt.GetType(), out IWorkflowEventChain? chain))
                {
                    handled = await chain.RaiseAsync(evt, cancellationToken).ConfigureAwait(false);
                }

                // If we reach the base WorkflowEvent type, stop looking further.
                if (eventType == typeof(WorkflowEvent))
                {
                    break;
                }

                eventType = eventType.BaseType;
            }
        }
    }

    public CheckpointInfo? LastCheckpoint { get; private set; }
}

internal static class Sample
{
    public static async ValueTask RunAsync()
    {
        WorkflowBuilder builder = new("start");
        // build the workflow

        Workflow workflow = builder.Build();

        StreamingRunWatcher watcher = new();
        watcher.RequestInfo += (evt) =>
        {
            // handle the request
            return false;
        };

        watcher.AgentRunUpdate += (evt) =>
        {
            Console.Write(evt.Update.Text);
            return true;
        };

        watcher.For<WorkflowEvent>().Event += (evt) =>
        {
            // log the event
            return false;
        };

        StreamingRun streamingRun = await InProcessExecution.Concurrent
                                                            .StreamAsync(workflow, input: "some input")
                                                            .ConfigureAwait(false);
        await watcher.RunToHaltAsync(streamingRun).ConfigureAwait(false);
    }
}
