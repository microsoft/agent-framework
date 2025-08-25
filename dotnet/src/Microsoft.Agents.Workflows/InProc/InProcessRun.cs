// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.InProc;

/// <summary>
/// Provides a local, in-process runner for executing a workflow using the specified input type.
/// </summary>
/// <remarks><para> <see cref="InProcessRun{TInput}"/> enables step-by-step execution of a workflow graph entirely
/// within the current process, without distributed coordination. It is primarily intended for testing, debugging, or
/// scenarios where workflow execution does not require executor distribution. </para></remarks>
/// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
internal class InProcessRun<TInput> : IAsyncRunHandle where TInput : notnull
{
    public InProcessRun(Workflow<TInput> workflow)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext<TInput>(workflow);

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId);
    }

    public async ValueTask<bool> IsValidInputTypeAsync<TMessage>(CancellationToken cancellation = default)
    {
        Type type = typeof(TMessage);

        // Short circuit the logic if the type is the input type
        if (type == typeof(TInput))
        {
            return true;
        }

        Executor startingExecutor = await this.RunContext.EnsureExecutorAsync(this.Workflow.StartExecutorId).ConfigureAwait(false);
        return startingExecutor.CanHandle(type);
    }

    public async ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellation) where T : notnull
    {
        // Check that the type of the incoming message is compatible with the starting executor's
        // input type.
        if (!await this.IsValidInputTypeAsync<T>(cancellation).ConfigureAwait(false))
        {
            return false;
        }

        await this.RunContext.AddExternalMessageAsync<T>(message).ConfigureAwait(false);
        return true;
    }

    public ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellation)
    {
        return this.RunContext.AddExternalMessageAsync(response);
    }

    private Workflow<TInput> Workflow { get; init; }
    private InProcessRunnerContext<TInput> RunContext { get; init; }
    private EdgeMap EdgeMap { get; init; }

    private ValueTask<IEnumerable<object?>> RouteExternalMessageAsync(MessageEnvelope envelope)
    {
        Debug.Assert(envelope.TargetId == null, "External Messages cannot be targeted to a specific executor.");

        object message = envelope.Message;
        return message is ExternalResponse response
            ? this.CompleteExternalResponseAsync(response)
            : this.EdgeMap.InvokeInputAsync(envelope);
    }

    private ValueTask<IEnumerable<object?>> CompleteExternalResponseAsync(ExternalResponse response)
    {
        if (!this.RunContext.CompleteRequest(response.RequestId))
        {
            throw new InvalidOperationException($"No pending request with ID {response.RequestId} found in the workflow context.");
        }

        return this.EdgeMap.InvokeResponseAsync(response);
    }

    private readonly InitLocked<Task> _runTask = new();
    private readonly InitLocked<Task> _untilHaltTask = new();

    public async ValueTask StartAsync(TInput input, CancellationToken token)
    {
        await this.EnqueueMessageAsync(input, token).ConfigureAwait(false);
        this._runTask.Init(RunLoopAsync);

        async Task RunLoopAsync()
        {
            this._runStatus = RunStatus.Running;

            try
            {
                while (!token.IsCancellationRequested && !this.RunContext.RaisedCompletion)
                {
                    //this._untilHaltTask.Init(RunToHaltAsync);
                    //await this._untilHaltTask.Get()!.ConfigureAwait(false);
                    while (this.RunContext.NextStepHasActions && !token.IsCancellationRequested && !this.RunContext.RaisedCompletion)
                    {
                        StepContext currentStep = this.RunContext.Advance();
                        await this.RunSuperstepAsync(currentStep).ConfigureAwait(false);
                    }

                    // We are in a halted state. Signal the halt to the EventStream, and then wait for new input.
                    this._runStatus = this.RunContext.HasUnservicedRequests ? RunStatus.PendingRequests : RunStatus.Idle;
                    this.RunContext.WorkflowEvents.SignalHalt();

                    await this.RunContext.JoinWaitUntilInputAsync(token).ConfigureAwait(false);
                    this._runStatus = RunStatus.Running;
                }
            }
            finally
            {
                this._runStatus = RunStatus.Completed;
            }
        }

        //async Task RunToHaltAsync()
        //{
        //    while (this.RunContext.NextStepHasActions && !token.IsCancellationRequested && !this.RunContext.RaisedCompletion)
        //    {
        //        StepContext currentStep = this.RunContext.Advance();
        //        await this.RunSuperstepAsync(currentStep).ConfigureAwait(false);
        //    }
        //}
    }

    private RunStatus _runStatus = RunStatus.Idle;
    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation)
    {
        return new(this._runStatus);
    }

    public async ValueTask<RunStatus> JoinUntilHaltAsync(CancellationToken cancellation)
    {
        Task? maybeTask = this._untilHaltTask.Get();
        if (maybeTask != null)
        {
            await maybeTask.ConfigureAwait(false);
        }

        return await this.GetStatusAsync(cancellation).ConfigureAwait(false);
    }

    public async IAsyncEnumerable<WorkflowEvent> ForwardEventsAsync(bool breakOnHalt, [EnumeratorCancellation] CancellationToken cancellation)
    {
        while (true)
        {
            await foreach (WorkflowEvent evt in this.RunContext.WorkflowEvents.JoinStreamAsync(cancellation)
                                                                              .WithCancellation(cancellation)
                                                                              .ConfigureAwait(false))
            {
                yield return evt;
            }

            if (breakOnHalt || this._runStatus == RunStatus.Completed || cancellation.IsCancellationRequested)
            {
                yield break;
            }
            else if (!breakOnHalt)
            {
                await this.RunContext.WorkflowEvents.JoinWaitForEventAsync(cancellation).ConfigureAwait(false);
            }
        }
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep)
    {
        // Deliver the messages and queue the next step
        List<Task<IEnumerable<object?>>> edgeTasks = new();
        foreach (ExecutorIdentity sender in currentStep.QueuedMessages.Keys)
        {
            IEnumerable<MessageEnvelope> senderMessages = currentStep.QueuedMessages[sender];
            if (sender.Id is null)
            {
                edgeTasks.AddRange(senderMessages.Select(envelope => this.RouteExternalMessageAsync(envelope).AsTask()));
            }
            else if (this.Workflow.Edges.TryGetValue(sender.Id!, out HashSet<Edge>? outgoingEdges))
            {
                foreach (Edge outgoingEdge in outgoingEdges)
                {
                    edgeTasks.AddRange(senderMessages.Select(envelope => this.EdgeMap.InvokeEdgeAsync(outgoingEdge, sender.Id, envelope).AsTask()));
                }
            }
        }

        // TODO: Should we let the user specify that they want strictly turn-based execution of the edges, vs. concurrent?
        // (Simply substitute a strategy that replaces Task.WhenAll with a loop with an await in the middle. Difficulty is
        // that we would need to avoid firing the tasks when we call InvokeEdgeAsync, or RouteExternalMessageAsync.
        IEnumerable<object?> results = (await Task.WhenAll(edgeTasks).ConfigureAwait(false)).SelectMany(r => r);

        // Commit the state updates (so they are visible to the next step)
        await this.RunContext.StateManager.PublishUpdatesAsync().ConfigureAwait(false);
    }
}

internal class InProcessRunner<TInput, TResult> : IRunHandleWithOutput<TResult> where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly InProcessRun<TInput> _run;

    public InProcessRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._run = new InProcessRun<TInput>(workflow);
    }

    public ValueTask StartAsync(TInput input, CancellationToken cancellation = default)
        => this._run.StartAsync(input, cancellation);

    public ValueTask<TResult?> GetRunningOutputAsync(CancellationToken cancellation = default)
    {
        return new(this._workflow.RunningOutput);
    }

    /// <inheritdoc cref="Workflow{TInput, TResult}.RunningOutput"/>
    public TResult? RunningOutput => this._workflow.RunningOutput;

    public IAsyncRunHandle RunHandle => this._run;
}
