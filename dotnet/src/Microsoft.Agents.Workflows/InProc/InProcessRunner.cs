// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
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
internal sealed class InProcessRunner<TInput> : ISuperStepRunner, ICheckpointingRunner where TInput : notnull
{
    public InProcessRunner(Workflow<TInput> workflow, ICheckpointManager? checkpointManager, string? runId = null)
    {
        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext<TInput>(workflow);
        this.CheckpointManager = checkpointManager;
        this.RunId = runId ?? Guid.NewGuid().ToString("N");

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId, this.StepTracer);
    }

    public string RunId { get; }

    public async ValueTask<bool> IsValidInputAsync<TMessage>(TMessage message)
    {
        Throw.IfNull(message);

        Type type = typeof(TMessage);

        // Short circuit the logic if the type is the input type
        if (type == typeof(TInput))
        {
            return true;
        }

        Executor startingExecutor = await this.RunContext.EnsureExecutorAsync(this.Workflow.StartExecutorId, tracer: null).ConfigureAwait(false);
        return startingExecutor.CanHandle(type);
    }

    async ValueTask<bool> ISuperStepRunner.EnqueueMessageAsync<T>(T message)
    {
        // Check that the type of the incoming message is compatible with the starting executor's
        // input type.
        if (!await this.IsValidInputAsync(message).ConfigureAwait(false))
        {
            return false;
        }

        await this.RunContext.AddExternalMessageAsync(message).ConfigureAwait(false);
        return true;
    }

    ValueTask ISuperStepRunner.EnqueueResponseAsync(ExternalResponse response)
    {
        return this.RunContext.AddExternalMessageAsync(response);
    }

    private InProcStepTracer StepTracer { get; } = new();
    private Workflow<TInput> Workflow { get; init; }
    private InProcessRunnerContext<TInput> RunContext { get; init; }
    private ICheckpointManager? CheckpointManager { get; }
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

    private ValueTask<IEnumerable<object?>> RouteExternalMessageAsync(MessageEnvelope envelope)
    {
        Debug.Assert(envelope.TargetId is null, "External Messages cannot be targeted to a specific executor.");

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

    public async ValueTask<StreamingRun> ResumeStreamAsync(CheckpointInfo checkpoint, CancellationToken cancellation = default)
    {
        Throw.IfNull(checkpoint);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This runner was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        await this.RestoreCheckpointAsync(checkpoint, cancellation).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    public async ValueTask<StreamingRun> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await this.RunContext.AddExternalMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    internal async ValueTask<Run> ResumeAsync(CheckpointInfo checkpoint, CancellationToken cancellation = default)
    {
        StreamingRun streamingRun = await this.ResumeStreamAsync(checkpoint, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    public async ValueTask<Run> RunAsync(TInput input, CancellationToken cancellation = default)
    {
        StreamingRun streamingRun = await this.StreamAsync(input, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    bool ISuperStepRunner.HasUnservicedRequests => this.RunContext.HasUnservicedRequests;
    bool ISuperStepRunner.HasUnprocessedMessages => this.RunContext.NextStepHasActions;

    public IReadOnlyList<CheckpointInfo> Checkpoints => this._checkpoints;

    async ValueTask<bool> ISuperStepRunner.RunSuperStepAsync(CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();

        StepContext currentStep = this.RunContext.Advance();

        if (currentStep.HasMessages)
        {
            await this.RunSuperstepAsync(currentStep).ConfigureAwait(false);
            return true;
        }

        this.EmitPendingEvents();
        return false;
    }

    private void EmitPendingEvents()
    {
        if (this.RunContext.QueuedEvents.Count > 0)
        {
            foreach (WorkflowEvent @event in this.RunContext.QueuedEvents)
            {
                this.RaiseWorkflowEvent(@event);
            }
            this.RunContext.QueuedEvents.Clear();
        }
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep)
    {
        this.RaiseWorkflowEvent(this.StepTracer.Advance(currentStep));

        // Deliver the messages and queue the next step
        List<Task<IEnumerable<object?>>> edgeTasks = [];
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

        // After the message handler invocations, we may have some events to deliver
        this.EmitPendingEvents();

        await this.CheckpointAsync().ConfigureAwait(false);

        this.RaiseWorkflowEvent(this.StepTracer.Complete(this.RunContext.NextStepHasActions, this.RunContext.HasUnservicedRequests));
    }

    private WorkflowInfo? _workflowInfoCache;
    private readonly List<CheckpointInfo> _checkpoints = [];
    internal async ValueTask CheckpointAsync(CancellationToken cancellation = default)
    {
        if (this.CheckpointManager is null)
        {
            // Always publish the state updates, even in the absence of a CheckpointManager.
            await this.RunContext.StateManager.PublishUpdatesAsync(this.StepTracer).ConfigureAwait(false);
            return;
        }

        // Notify all the executors that they should prepare for checkpointing.
        Task prepareTask = this.RunContext.PrepareForCheckpointAsync(cancellation);

        // Create a representation of the current workflow if it does not already exist.
        this._workflowInfoCache ??= this.Workflow.ToWorkflowInfo();

        Dictionary<EdgeId, PortableValue> edgeData = await this.EdgeMap.ExportStateAsync().ConfigureAwait(false);

        await prepareTask.ConfigureAwait(false);
        await this.RunContext.StateManager.PublishUpdatesAsync(this.StepTracer).ConfigureAwait(false);

        RunnerStateData runnerData = await this.RunContext.ExportStateAsync().ConfigureAwait(false);
        Dictionary<ScopeKey, PortableValue> stateData = await this.RunContext.StateManager.ExportStateAsync().ConfigureAwait(false);

        Checkpoint checkpoint = new(this.StepTracer.StepNumber, this._workflowInfoCache, runnerData, stateData, edgeData);
        CheckpointInfo checkpointInfo = await this.CheckpointManager.CommitCheckpointAsync(this.RunId, checkpoint).ConfigureAwait(false);
        this.StepTracer.TraceCheckpointCreated(checkpointInfo);
        this._checkpoints.Add(checkpointInfo);
    }

    public async ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellation = default)
    {
        Throw.IfNull(checkpointInfo);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This run was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        Checkpoint checkpoint = await this.CheckpointManager.LookupCheckpointAsync(this.RunId, checkpointInfo)
                                                            .ConfigureAwait(false);

        // Validate the checkpoint is compatible with this workflow
        if (!this.CheckWorkflowMatch(checkpoint))
        {
            // TODO: ArgumentException?
            throw new InvalidDataException("The specified checkpoint is not compatible with the workflow associated with this runner.");
        }

        await this.RunContext.StateManager.ImportStateAsync(checkpoint).ConfigureAwait(false);
        await this.RunContext.ImportStateAsync(checkpoint).ConfigureAwait(false);

        Task executorNotifyTask = this.RunContext.NotifyCheckpointLoadedAsync(cancellation);
        ValueTask republishRequestsTask = this.RunContext.RepublishUnservicedRequestsAsync(cancellation);

        await this.EdgeMap.ImportStateAsync(checkpoint).ConfigureAwait(false);
        await Task.WhenAll(executorNotifyTask, republishRequestsTask.AsTask()).ConfigureAwait(false);

        this.StepTracer.Reload(this.StepTracer.StepNumber);
    }

    private bool CheckWorkflowMatch(Checkpoint checkpoint) =>
        checkpoint.Workflow.IsMatch(this.Workflow);
}

internal sealed class InProcessRunner<TInput, TResult> : IRunnerWithOutput<TResult>, ICheckpointingRunner where TInput : notnull
{
    private readonly Workflow<TInput, TResult> _workflow;
    private readonly InProcessRunner<TInput> _innerRunner;

    public InProcessRunner(Workflow<TInput, TResult> workflow, CheckpointManager? checkpointManager, string? runId = null)
    {
        this._workflow = Throw.IfNull(workflow);

        this._innerRunner = new(workflow, checkpointManager, runId);
    }

    internal async ValueTask<StreamingRun<TResult>> ResumeStreamAsync(CheckpointInfo checkpoint, CancellationToken cancellation = default)
    {
        await this._innerRunner.ResumeStreamAsync(checkpoint, cancellation).ConfigureAwait(false);

        return new StreamingRun<TResult>(this);
    }

    public async ValueTask<StreamingRun<TResult>> StreamAsync(TInput input, CancellationToken cancellation = default)
    {
        await ((ISuperStepRunner)this._innerRunner).EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun<TResult>(this);
    }

    public async ValueTask<Run<TResult>> ResumeAsync(CheckpointInfo checkpoint, CancellationToken cancellation = default)
    {
        StreamingRun<TResult> streamingRun = await this.ResumeStreamAsync(checkpoint, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run<TResult>.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    public async ValueTask<Run<TResult>> RunAsync(TInput input, CancellationToken cancellation = default)
    {
        StreamingRun<TResult> streamingRun = await this.StreamAsync(input, cancellation).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();

        return await Run<TResult>.CaptureStreamAsync(streamingRun, cancellation).ConfigureAwait(false);
    }

    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellation = default)
        => this._innerRunner.RestoreCheckpointAsync(checkpointInfo, cancellation);

    internal ValueTask CheckpointAsync() => this._innerRunner.CheckpointAsync();

    /// <inheritdoc cref="Workflow{TInput, TResult}.RunningOutput"/>
    public TResult? RunningOutput => this._workflow.RunningOutput;

    ISuperStepRunner IRunnerWithOutput<TResult>.StepRunner => this._innerRunner;

    public IReadOnlyList<CheckpointInfo> Checkpoints => this._innerRunner.Checkpoints;
}
