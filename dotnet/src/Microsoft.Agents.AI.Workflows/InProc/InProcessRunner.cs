// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.InProc;

/// <summary>
/// Provides a local, in-process runner for executing a workflow using the specified input type.
/// </summary>
/// <remarks><para> <see cref="InProcessRunner"/> enables step-by-step execution of a workflow graph entirely
/// within the current process, without distributed coordination. It is primarily intended for testing, debugging, or
/// scenarios where workflow execution does not require executor distribution. </para></remarks>
internal sealed class InProcessRunner : ISuperStepRunner, ICheckpointingRunner
{
    public InProcessRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? runId = null, object? workflowOwnership = null, bool subworkflow = false, params Type[] knownValidInputTypes)
    {
        this.RunId = runId ?? Guid.NewGuid().ToString("N");
        this.StartExecutorId = workflow.StartExecutorId;

        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext(workflow, this.RunId, withCheckpointing: checkpointManager != null, this.StepTracer, workflowOwnership, subworkflow);
        this.CheckpointManager = checkpointManager;

        this._knownValidInputTypes = [.. knownValidInputTypes];

        // Initialize the runners for each of the edges, along with the state for edges that
        // need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId, this.StepTracer);
    }

    /// <inheritdoc cref="ISuperStepRunner.RunId"/>
    public string RunId { get; }

    /// <inheritdoc cref="ISuperStepRunner.StartExecutorId"/>
    public string StartExecutorId { get; }

    private readonly HashSet<Type> _knownValidInputTypes;
    public async ValueTask<bool> IsValidInputTypeAsync(Type messageType)
    {
        if (this._knownValidInputTypes.Contains(messageType))
        {
            return true;
        }

        Executor startingExecutor = await this.RunContext.EnsureExecutorAsync(this.Workflow.StartExecutorId, tracer: null).ConfigureAwait(false);
        if (startingExecutor.CanHandle(messageType))
        {
            this._knownValidInputTypes.Add(messageType);
            return true;
        }

        return false;
    }

    public async ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(message);

        if (message is ExternalResponse response)
        {
            await this.RunContext.AddExternalResponseAsync(response).ConfigureAwait(false);
        }

        // Check that the type of the incoming message is compatible with the starting executor's
        // input type.
        if (!await this.IsValidInputTypeAsync(declaredType).ConfigureAwait(false))
        {
            return false;
        }

        await this.RunContext.AddExternalMessageAsync(message, declaredType).ConfigureAwait(false);
        return true;
    }

    public ValueTask<bool> EnqueueMessageAsync<T>(T message)
        => this.EnqueueMessageUntypedAsync(Throw.IfNull(message), typeof(T));

    public ValueTask<bool> EnqueueMessageAsync(object message)
        => this.EnqueueMessageUntypedAsync(Throw.IfNull(message), message.GetType());

    ValueTask ISuperStepRunner.EnqueueResponseAsync(ExternalResponse response)
    {
        // TODO: Check that there exists a corresponding input port?
        return this.RunContext.AddExternalResponseAsync(response);
    }

    private InProcStepTracer StepTracer { get; } = new();
    private Workflow Workflow { get; init; }
    internal InProcessRunnerContext RunContext { get; init; }
    private ICheckpointManager? CheckpointManager { get; }
    private EdgeMap EdgeMap { get; init; }

    public event EventHandler<WorkflowEvent>? WorkflowEvent;

    private void RaiseWorkflowEvent(WorkflowEvent workflowEvent)
    {
        this.WorkflowEvent?.Invoke(this, workflowEvent);
    }

    public async ValueTask<StreamingRun> ResumeStreamAsync(CheckpointInfo checkpoint, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(checkpoint);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This runner was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        await this.RestoreCheckpointAsync(checkpoint, cancellationToken).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    public async ValueTask<StreamingRun> StreamAsync(object input, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        await this.EnqueueMessageUntypedAsync(input, input.GetType()).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    public async ValueTask<StreamingRun> StreamAsync<TInput>(TInput input, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        await this.EnqueueMessageAsync(input).ConfigureAwait(false);

        return new StreamingRun(this);
    }

    internal async ValueTask<Run> ResumeAsync(CheckpointInfo checkpoint, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        StreamingRun streamingRun = await this.ResumeStreamAsync(checkpoint, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<Run> RunAsync(object input, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        StreamingRun streamingRun = await this.StreamAsync(input, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<Run> RunAsync<TInput>(TInput input, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        StreamingRun streamingRun = await this.StreamAsync(input, cancellationToken).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();

        return await Run.CaptureStreamAsync(streamingRun, cancellationToken).ConfigureAwait(false);
    }

    bool ISuperStepRunner.HasUnservicedRequests => this.RunContext.HasUnservicedRequests;
    bool ISuperStepRunner.HasUnprocessedMessages => this.RunContext.NextStepHasActions;

    public IReadOnlyList<CheckpointInfo> Checkpoints => this._checkpoints;

    async ValueTask<bool> ISuperStepRunner.RunSuperStepAsync(CancellationToken cancellationToken)
    {
        this.RunContext.CheckEnded();
        if (cancellationToken.IsCancellationRequested)
        {
            return false;
        }

        StepContext currentStep = await this.RunContext.AdvanceAsync().ConfigureAwait(false);

        if (currentStep.HasMessages ||
            this.RunContext.HasQueuedExternalDeliveries ||
            this.RunContext.JoinedRunnersHaveActions)
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

    private async ValueTask DeliverMessagesAsync(string receiverId, List<MessageEnvelope> envelopes)
    {
        Executor executor = await this.RunContext.EnsureExecutorAsync(receiverId, this.StepTracer).ConfigureAwait(false);

        this.StepTracer.TraceActivated(receiverId);
        foreach (MessageEnvelope envelope in envelopes)
        {
            await executor.ExecuteAsync(
                envelope.Message,
                envelope.MessageType,
                this.RunContext.Bind(receiverId, envelope.TraceContext)
            ).ConfigureAwait(false);
        }
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep)
    {
        this.RaiseWorkflowEvent(this.StepTracer.Advance(currentStep));

        // Deliver the messages and queue the next step
        List<Task> receiverTasks =
            currentStep.QueuedMessages.Keys
                       .Select(receiverId => this.DeliverMessagesAsync(receiverId, currentStep.MessagesFor(receiverId)).AsTask())
                       .ToList();

        // TODO: Should we let the user specify that they want strictly turn-based execution of the edges, vs. concurrent?
        // (Simply substitute a strategy that replaces Task.WhenAll with a loop with an await in the middle. Difficulty is
        // that we would need to avoid firing the tasks when we call InvokeEdgeAsync, or RouteExternalMessageAsync.
        await Task.WhenAll(receiverTasks).ConfigureAwait(false);

        // When we have sub-workflows, sending a message to the WorkflowHostExecutor will only queue it into the
        // subworkflow's input queue. In order to actually process the message and align the supersteps correctly,
        // we need to drive the superstep of the subworkflow here.
        // TODO: Investigate if we can fully pull in the subworkflow execution into the WorkflowHostExecutor itself.
        List<Task> subworkflowTasks = new();
        foreach (ISuperStepRunner subworkflowRunner in this.RunContext.JoinedSubworkflowRunners)
        {
            subworkflowTasks.Add(subworkflowRunner.RunSuperStepAsync(CancellationToken.None).AsTask());
        }

        await Task.WhenAll(subworkflowTasks).ConfigureAwait(false);

        // After the message handler invocations, we may have some events to deliver
        this.EmitPendingEvents();

        await this.CheckpointAsync().ConfigureAwait(false);

        this.RaiseWorkflowEvent(this.StepTracer.Complete(this.RunContext.NextStepHasActions, this.RunContext.HasUnservicedRequests));
    }

    private WorkflowInfo? _workflowInfoCache;
    private readonly List<CheckpointInfo> _checkpoints = [];
    internal async ValueTask CheckpointAsync(CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        if (this.CheckpointManager is null)
        {
            // Always publish the state updates, even in the absence of a CheckpointManager.
            await this.RunContext.StateManager.PublishUpdatesAsync(this.StepTracer).ConfigureAwait(false);
            return;
        }

        // Notify all the executors that they should prepare for checkpointing.
        Task prepareTask = this.RunContext.PrepareForCheckpointAsync(cancellationToken);

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

    public async ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
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

        Task executorNotifyTask = this.RunContext.NotifyCheckpointLoadedAsync(cancellationToken);
        ValueTask republishRequestsTask = this.RunContext.RepublishUnservicedRequestsAsync(cancellationToken);

        await this.EdgeMap.ImportStateAsync(checkpoint).ConfigureAwait(false);
        await Task.WhenAll(executorNotifyTask, republishRequestsTask.AsTask()).ConfigureAwait(false);

        this.StepTracer.Reload(this.StepTracer.StepNumber);
    }

    private bool CheckWorkflowMatch(Checkpoint checkpoint) =>
        checkpoint.Workflow.IsMatch(this.Workflow);

    public ValueTask RequestEndRunAsync() => this.RunContext.EndRunAsync();
}
