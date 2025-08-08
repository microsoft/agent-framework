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
/// Provides a local, in-process runner for executing a workflow using the specified input type.
/// </summary>
/// <remarks><para> <see cref="LocalRunner{TInput}"/> enables step-by-step execution of a workflow graph entirely
/// within the current process, without distributed coordination. It is primarily intended for testing, debugging, or
/// scenarios where workflow execution does not require executor distribution. </para></remarks>
/// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
public class LocalRunner<TInput> : ISuperStepRunner where TInput : notnull
{
    /// <summary>
    /// Initializes a new instance of the <see cref="LocalRunner{TInput}"/> class to execute the specified workflow
    /// locally.
    /// </summary>
    /// <remarks>The <see cref="LocalRunner{TInput}"/> manages the execution context and edge mapping for the
    /// provided workflow, enabling local, in-process execution. The workflow's structure, including its edges and
    /// ports, is used to set up the runner's internal state.</remarks>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
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
    /// Initiates an asynchronous streaming execution using the specified input.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun"/> provides methods to observe and control
    /// the ongoing streaming execution. The operation will continue until the streaming execution is finished or
    /// cancelled.</remarks>
    /// <param name="input">The input message to be processed as part of the streaming run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    public async ValueTask<StreamingRun> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
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
/// Provides a local, in-process runner for executing a workflow with input and producing a result.
/// </summary>
/// <remarks><para> <see cref="LocalRunner{TInput, TResult}"/> manages the execution of a <see
/// cref="Workflow{TInput, TResult}"/> instance locally, allowing for streaming input and asynchronous result retrieval.
/// </para> <para> This class is intended for scenarios where workflow execution does not require distributed procesing.
/// It supports streaming execution and exposes methods to retrieve the final result asynchronously.
/// </para></remarks>
/// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
/// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
public class LocalRunner<TInput, TResult> : IRunnerWithOutput<TResult> where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly ISuperStepRunner _innerRunner;

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalRunner{TInput, TResult}"/> class to execute the specified
    /// workflow locally.
    /// </summary>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    public LocalRunner(Workflow<TInput, TResult> workflow)
    {
        this._workflow = Throw.IfNull(workflow);
        this._innerRunner = new LocalRunner<TInput>(workflow);
    }

    /// <summary>
    /// Initiates an asynchronous streaming execution for the specified input.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun{TResult}"/> can be used to retrieve results
    /// as they become available. If the operation is cancelled via the <paramref name="cancellation"/> token, the
    /// streaming execution will be terminated.</remarks>
    /// <param name="input">The input value to be processed by the streaming run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="StreamingRun{TResult}"/> that provides access to the results of the streaming
    /// run.</returns>
    public async ValueTask<StreamingRun<TResult>> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this._innerRunner.EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun<TResult>(this);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public async ValueTask<Run> RunAsync(TInput input, CancellationToken cancellation = default)
    {
        StreamingRun<TResult> streamingRun = await this.StreamAsync(input, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run<TResult>.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    /// <inheritdoc cref="Workflow{TInput, TResult}.RunningOutput"/>
    public TResult? RunningOutput => this._workflow.RunningOutput;

    ISuperStepRunner IRunnerWithOutput<TResult>.StepRunner => this._innerRunner;
}
