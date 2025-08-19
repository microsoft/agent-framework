// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.InProc;

/// <summary>
/// Provides a local, in-process runner for executing a workflow using the specified input type.
/// </summary>
/// <remarks><para> <see cref="InProcessRunner{TInput}"/> enables step-by-step execution of a workflow graph entirely
/// within the current process, without distributed coordination. It is primarily intended for testing, debugging, or
/// scenarios where workflow execution does not require executor distribution. </para></remarks>
/// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
internal class InProcessRunner<TInput> : ISuperStepRunner where TInput : notnull
{
    public InProcessRunner(Workflow<TInput> workflow)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext<TInput>(workflow);

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId);
    }

    ValueTask ISuperStepRunner.EnqueueMessageAsync(object message)
    {
        return this.RunContext.AddExternalMessageAsync(message);
    }

    private Dictionary<string, string> PendingCalls { get; } = new();
    private Workflow<TInput> Workflow { get; init; }
    private InProcessRunnerContext<TInput> RunContext { get; init; }
    private EdgeMap EdgeMap { get; init; }

    event EventHandler<WorkflowEvent>? ISuperStepRunner.WorkflowEvent
    {
        add => this.WorkflowEvent += value;
        remove => this.WorkflowEvent -= value;
    }

    private event EventHandler<WorkflowEvent>? WorkflowEvent;

    private void RaiseWorkflowEvent(WorkflowEvent workflowEvent)
    {
        this.WorkflowEvent?.Invoke(this, workflowEvent);
    }

    private bool IsResponse(object message)
    {
        return message is ExternalResponse;
    }

    private ValueTask<IEnumerable<object?>> RouteExternalMessageAsync(object message)
    {
        return message is ExternalResponse response
            ? this.CompleteExternalResponseAsync(response)
            : this.EdgeMap.InvokeInputAsync(message);
    }

    private ValueTask<IEnumerable<object?>> CompleteExternalResponseAsync(ExternalResponse response)
    {
        if (!this.RunContext.CompleteRequest(response.RequestId))
        {
            throw new InvalidOperationException($"No pending request with ID {response.RequestId} found in the workflow context.");
        }

        return this.EdgeMap.InvokeResponseAsync(response);
    }

    public async ValueTask<StreamingRun> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    public async ValueTask<Run> RunAsync(TInput input, CancellationToken cancellation = default)
    {
        StreamingRun streamingRun = await this.StreamAsync(input, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    bool ISuperStepRunner.HasUnservicedRequests => this.RunContext.HasUnservicedRequests;
    bool ISuperStepRunner.HasUnprocessedMessages => this.RunContext.NextStepHasActions;

    async ValueTask<bool> ISuperStepRunner.RunSuperStepAsync(CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();

        StepContext currentStep = this.RunContext.Advance();

        if (currentStep.HasMessages)
        {
            await this.RunSuperstepAsync(currentStep).ConfigureAwait(false);
            return true;
        }

        return false;
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep)
    {
        // Deliver the messages and queue the next step
        List<Task<IEnumerable<object?>>> edgeTasks = new();
        foreach (ExecutorIdentity sender in currentStep.QueuedMessages.Keys)
        {
            IEnumerable<object> senderMessages = currentStep.QueuedMessages[sender];
            if (sender.Id is null)
            {
                edgeTasks.AddRange(senderMessages.Select(message => this.RouteExternalMessageAsync(message).AsTask()));
            }
            else if (this.Workflow.Edges.TryGetValue(sender.Id!, out HashSet<Edge>? outgoingEdges))
            {
                foreach (Edge outgoingEdge in outgoingEdges)
                {
                    edgeTasks.AddRange(senderMessages.Select(message => this.EdgeMap.InvokeEdgeAsync(outgoingEdge, sender.Id, message).AsTask()));
                }
            }
        }

        // TODO: Should we let the user specify that they want strictly turn-based execution of the edges, vs. concurrent?
        // (Simply substitute a strategy that replaces Task.WhenAll with a loop with an await in the middle. Difficulty is
        // that we would need to avoid firing the tasks when we call InvokeEdgeAsync, or RouteExternalMessageAsync.
        IEnumerable<object?> results = (await Task.WhenAll(edgeTasks).ConfigureAwait(false)).SelectMany(r => r);

        // Commit the state updates (so they are visible to the next step)
        await this.RunContext.StateManager.PublishUpdatesAsync().ConfigureAwait(false);

        // After the message handler invocations, we may have some events to deliver
        foreach (WorkflowEvent @event in this.RunContext.QueuedEvents)
        {
            this.RaiseWorkflowEvent(@event);
        }

        this.RunContext.QueuedEvents.Clear();
    }
}

internal class InProcessRunner<TInput, TResult> : IRunnerWithOutput<TResult> where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly ISuperStepRunner _innerRunner;

    public InProcessRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._innerRunner = new InProcessRunner<TInput>(workflow);
    }

    public async ValueTask<StreamingRun<TResult>> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this._innerRunner.EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun<TResult>(this);
    }

    public async ValueTask<Run<TResult>> RunAsync(TInput input, CancellationToken cancellation = default)
    {
        StreamingRun<TResult> streamingRun = await this.StreamAsync(input, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run<TResult>.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    /// <inheritdoc cref="Workflow{TInput, TResult}.RunningOutput"/>
    public TResult? RunningOutput => this._workflow.RunningOutput;

    ISuperStepRunner IRunnerWithOutput<TResult>.StepRunner => this._innerRunner;
}
