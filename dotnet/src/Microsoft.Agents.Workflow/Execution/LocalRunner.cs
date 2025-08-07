// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

/// <summary>
/// .
/// </summary>
/// <typeparam name="TInput"></typeparam>
public class LocalRunner<TInput> : ISuperStepRunner where TInput : notnull
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="workflow"></param>
    public LocalRunner(Workflow<TInput> workflow)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new LocalRunnerContext<TInput>(workflow);

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
    private LocalRunnerContext<TInput> RunContext { get; init; }
    private EdgeMap EdgeMap { get; init; }

    // TODO: Better signature?
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

    /// <summary>
    /// .
    /// </summary>
    /// <param name="input"></param>
    /// <param name="cancellation"></param>
    /// <returns></returns>
    public async ValueTask<StreamingExecutionHandle> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        return new StreamingExecutionHandle(this);
    }

    private StepContext? _currentStep = null;
    async ValueTask<bool> ISuperStepRunner.RunSuperStepAsync(CancellationToken cancellation)
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

        // TODO: Commit the state updates (so they are visible to the next step)

        // After the message handler invocations, we may have some events to deliver
        foreach (WorkflowEvent @event in this.RunContext.QueuedEvents)
        {
            this.RaiseWorkflowEvent(@event);
        }

        this.RunContext.QueuedEvents.Clear();
    }
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="TInput"></typeparam>
/// <typeparam name="TResult"></typeparam>
public class LocalRunner<TInput, TResult> : IRunnerWithResult<TResult> where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly ISuperStepRunner _innerRunner;

    /// <summary>
    /// .
    /// </summary>
    /// <param name="workflow"></param>
    public LocalRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._innerRunner = new LocalRunner<TInput>(workflow);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="input"></param>
    /// <param name="cancellation"></param>
    /// <returns></returns>
    public async ValueTask<StreamingExecutionHandle> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this._innerRunner.EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingExecutionHandle(this._innerRunner);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="cancellation"></param>
    /// <returns></returns>
    public ValueTask<TResult> GetResultAsync(CancellationToken cancellation = default)
    {
        // TODO: Block on finishing consuming StreamAsync()?
        return new ValueTask<TResult>(this.RunningOutput!);
    }

    /// <summary>
    /// .
    /// </summary>
    public TResult? RunningOutput => this._workflow.RunningOutput;

    ISuperStepRunner IRunnerWithResult<TResult>.StepRunner => this._innerRunner;
}
