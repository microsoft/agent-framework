// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal class LocalRunner<TInput> : ISuperStepRunner where TInput : notnull
{
    public LocalRunner(Workflow<TInput> workflow)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new LocalRunnerContext<TInput>(workflow);

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.StartExecutorId);
    }

    ValueTask ISuperStepRunner.EnqueueMessageAsync(object message)
    {
        return this.RunContext.AddExternalMessageAsync(message);
    }

    protected Dictionary<string, string> PendingCalls { get; } = new();
    protected Workflow<TInput> Workflow { get; init; }
    protected LocalRunnerContext<TInput> RunContext { get; init; }
    protected EdgeMap EdgeMap { get; init; }

    // TODO: Better signature?
    public event EventHandler<WorkflowEvent>? WorkflowEvent;

    private void RaiseWorkflowEvent(WorkflowEvent workflowEvent)
    {
        this.WorkflowEvent?.Invoke(this, workflowEvent);
    }

    private bool IsResponse(object message)
    {
        return false;
    }

    private ValueTask<IEnumerable<CallResult?>> RouteExternalMessageAsync(object message)
    {
#pragma warning disable CS0219 // Variable is assigned but its value is never used
        bool isHil = false;
#pragma warning restore CS0219 // Variable is assigned but its value is never used

        return this.IsResponse(message)
            ? this.EdgeMap.InvokeResponseAsync(message)
            : this.EdgeMap.InvokeInputAsync(message);
    }

    public async ValueTask<StreamingExecutionHandle> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        return new StreamingExecutionHandle(this);
    }

    private StepContext? _currentStep = null;
    public async ValueTask<bool> RunSuperStepAsync(CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();

        if (this._currentStep == null)
        {
            // TODO: Python-side does not raise this event.
            // await this.RunContext.AddEventAsync(this.Workflow.StartExecutorId, new WorkflowStartedEvent()).ConfigureAwait(false);
            this._currentStep = this.RunContext.Advance();
        }

        if (this._currentStep.HasMessages)
        {
            await this.RunSuperstepAsync(this._currentStep).ConfigureAwait(false);
            this._currentStep = this.RunContext.Advance();

            return true;
        }

        return false;
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep)
    {
        // Deliver the messages and queue the next step
        List<Task<IEnumerable<CallResult?>>> edgeTasks = new();
        foreach (ExecutorIdentity sender in currentStep.QueuedMessages.Keys)
        {
            IEnumerable<object> senderMessages = currentStep.QueuedMessages[sender];
            if (sender.Id is null)
            {
                edgeTasks.AddRange(senderMessages.Select(message => this.RouteExternalMessageAsync(message).AsTask()));
            }
            else
            {
                HashSet<FlowEdge> outgoingEdges = this.Workflow.Edges[sender.Id!]; // Id is not null when Identity is not .None
                foreach (FlowEdge outgoingEdge in outgoingEdges)
                {
                    edgeTasks.AddRange(senderMessages.Select(message => this.EdgeMap.InvokeEdgeAsync(outgoingEdge, sender.Id, message).AsTask()));
                }
            }
        }

        // TODO: Should we let the user specify that they want strictly turn-based execution of the edges, vs. concurrent?
        // (Simply substitute a strategy that replaces Task.WhenAll with a loop with an await in the middle. Difficulty is
        // that we would need to avoid firing the tasks when we call InvokeEdgeAsync, or RouteExternalMessageAsync.
        IEnumerable<CallResult?> results = (await Task.WhenAll(edgeTasks).ConfigureAwait(false)).SelectMany(r => r);

        // TODO: Commit the state updates (so they are visible to the next step)

        // After the message handler invocations, we may have some events to deliver
        foreach (WorkflowEvent @event in this.RunContext.QueuedEvents)
        {
            this.RaiseWorkflowEvent(@event);
        }
    }
}

internal class LocalRunner<TInput, TResult> : IRunnerWithResult<TResult> where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly LocalRunner<TInput> _innerRunner;

    public LocalRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._innerRunner = new LocalRunner<TInput>(workflow);
    }

    public async ValueTask<StreamingExecutionHandle> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.StepRunner.EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingExecutionHandle(this._innerRunner);
    }

    public ValueTask<TResult> GetResultAsync(CancellationToken cancellation = default)
    {
        // TODO: Block on finishing consuming StreamAsync()?
        return new ValueTask<TResult>(this.RunningOutput!);
    }

    public TResult? RunningOutput => this._workflow.RunningOutput;

    public ISuperStepRunner StepRunner => this._innerRunner;
}
