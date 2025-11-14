// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
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
internal sealed class InProcessRunner : ISuperStepRunner, ICheckpointingHandle
{
    public static InProcessRunner CreateTopLevelRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? runId = null, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        return new InProcessRunner(workflow,
                                   checkpointManager,
                                   runId,
                                   enableConcurrentRuns: enableConcurrentRuns,
                                   knownValidInputTypes: knownValidInputTypes);
    }

    public static InProcessRunner CreateSubworkflowRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? runId = null, object? existingOwnerSignoff = null, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        return new InProcessRunner(workflow,
                                   checkpointManager,
                                   runId,
                                   existingOwnerSignoff: existingOwnerSignoff,
                                   enableConcurrentRuns: enableConcurrentRuns,
                                   knownValidInputTypes: knownValidInputTypes,
                                   subworkflow: true);
    }

    private InProcessRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? runId = null, object? existingOwnerSignoff = null, bool subworkflow = false, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        if (enableConcurrentRuns && !workflow.AllowConcurrent)
        {
            throw new InvalidOperationException("Workflow must only consist of cross-run share-capable or factory-created executors. Executors " +
                $"not supporting concurrent: {string.Join(", ", workflow.NonConcurrentExecutorIds)}");
        }

        this.RunId = runId ?? Guid.NewGuid().ToString("N");
        this.StartExecutorId = workflow.StartExecutorId;

        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext(workflow, this.RunId, withCheckpointing: checkpointManager != null, this.OutgoingEvents, this.StepTracer, existingOwnerSignoff, subworkflow, enableConcurrentRuns);
        this.CheckpointManager = checkpointManager;

        this._knownValidInputTypes = knownValidInputTypes != null
                                   ? [.. knownValidInputTypes]
                                   : [];

        // Initialize the runners for each of the edges, along with the state for edges that need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId, this.StepTracer);
    }

    /// <inheritdoc cref="ISuperStepRunner.RunId"/>
    public string RunId { get; }

    /// <inheritdoc cref="ISuperStepRunner.StartExecutorId"/>
    public string StartExecutorId { get; }

    private readonly HashSet<Type> _knownValidInputTypes;
    public async ValueTask<bool> IsValidInputTypeAsync(Type messageType, CancellationToken cancellationToken = default)
    {
        if (this._knownValidInputTypes.Contains(messageType))
        {
            return true;
        }

        Executor startingExecutor = await this.RunContext.EnsureExecutorAsync(this.Workflow.StartExecutorId, tracer: null, cancellationToken).ConfigureAwait(false);
        if (startingExecutor.CanHandle(messageType))
        {
            this._knownValidInputTypes.Add(messageType);
            return true;
        }

        return false;
    }

    public ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellationToken = default)
        => this.IsValidInputTypeAsync(typeof(T), cancellationToken);

    public async ValueTask<bool> EnqueueMessageUntypedAsync(object message, Type declaredType, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(message);

        if (message is ExternalResponse response)
        {
            await this.RunContext.AddExternalResponseAsync(response).ConfigureAwait(false);
        }

        // Check that the type of the incoming message is compatible with the starting executor's
        // input type.
        if (!await this.IsValidInputTypeAsync(declaredType, cancellationToken).ConfigureAwait(false))
        {
            return false;
        }

        await this.RunContext.AddExternalMessageAsync(message, declaredType).ConfigureAwait(false);
        return true;
    }

    public ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellationToken = default)
        => this.EnqueueMessageUntypedAsync(Throw.IfNull(message), typeof(T), cancellationToken);

    public ValueTask<bool> EnqueueMessageUntypedAsync(object message, CancellationToken cancellationToken = default)
        => this.EnqueueMessageUntypedAsync(Throw.IfNull(message), message.GetType(), cancellationToken);

    ValueTask ISuperStepRunner.EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellationToken)
    {
        // TODO: Check that there exists a corresponding input port?
        return this.RunContext.AddExternalResponseAsync(response);
    }

    private InProcStepTracer StepTracer { get; } = new();
    private Workflow Workflow { get; init; }
    internal InProcessRunnerContext RunContext { get; init; }
    private ICheckpointManager? CheckpointManager { get; }
    private EdgeMap EdgeMap { get; init; }

    public ConcurrentEventSink OutgoingEvents { get; } = new();

    private ValueTask RaiseWorkflowEventAsync(WorkflowEvent workflowEvent)
        => this.OutgoingEvents.EnqueueAsync(workflowEvent);

    public ValueTask<AsyncRunHandle> BeginStreamAsync(ExecutionMode mode, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        return new(new AsyncRunHandle(this, this, mode));
    }

    public async ValueTask<AsyncRunHandle> ResumeStreamAsync(ExecutionMode mode, CheckpointInfo fromCheckpoint, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(fromCheckpoint);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This runner was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        await this.RestoreCheckpointAsync(fromCheckpoint, cancellationToken).ConfigureAwait(false);
        return new AsyncRunHandle(this, this, mode);
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

        StepContext currentStep = await this.RunContext.AdvanceAsync(cancellationToken).ConfigureAwait(false);

        if (currentStep.HasMessages ||
            this.RunContext.HasQueuedExternalDeliveries ||
            this.RunContext.JoinedRunnersHaveActions)
        {
            try
            {
                await this.RunSuperstepAsync(currentStep, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            { }
            catch (Exception e)
            {
                await this.RaiseWorkflowEventAsync(new WorkflowErrorEvent(e)).ConfigureAwait(false);
            }

            return true;
        }

        return false;
    }

    private async ValueTask DeliverMessagesAsync(string receiverId, ConcurrentQueue<MessageEnvelope> envelopes, CancellationToken cancellationToken)
    {
        Executor executor = await this.RunContext.EnsureExecutorAsync(receiverId, this.StepTracer, cancellationToken).ConfigureAwait(false);

        this.StepTracer.TraceActivated(receiverId);
        while (envelopes.TryDequeue(out var envelope))
        {
            await executor.ExecuteAsync(
                envelope.Message,
                envelope.MessageType,
                this.RunContext.Bind(receiverId, envelope.TraceContext),
                cancellationToken
            ).ConfigureAwait(false);
        }
    }

    private async ValueTask RunSuperstepAsync(StepContext currentStep, CancellationToken cancellationToken)
    {
        await this.RaiseWorkflowEventAsync(this.StepTracer.Advance(currentStep)).ConfigureAwait(false);

        // Deliver the messages and queue the next step
        List<Task> receiverTasks =
            currentStep.QueuedMessages.Keys
                       .Select(receiverId => this.DeliverMessagesAsync(receiverId, currentStep.MessagesFor(receiverId), cancellationToken).AsTask())
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
            subworkflowTasks.Add(subworkflowRunner.RunSuperStepAsync(cancellationToken).AsTask());
        }

        await Task.WhenAll(subworkflowTasks).ConfigureAwait(false);

        await this.CheckpointAsync(cancellationToken).ConfigureAwait(false);

        await this.RaiseWorkflowEventAsync(this.StepTracer.Complete(this.RunContext.NextStepHasActions, this.RunContext.HasUnservicedRequests))
                  .ConfigureAwait(false);
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
