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
using Microsoft.Agents.AI.Workflows.Observability;
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
    public static InProcessRunner CreateTopLevelRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? sessionId = null, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        return new InProcessRunner(workflow,
                                   checkpointManager,
                                   sessionId,
                                   enableConcurrentRuns: enableConcurrentRuns,
                                   knownValidInputTypes: knownValidInputTypes);
    }

    public static InProcessRunner CreateSubworkflowRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? sessionId = null, object? existingOwnerSignoff = null, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        return new InProcessRunner(workflow,
                                   checkpointManager,
                                   sessionId,
                                   existingOwnerSignoff: existingOwnerSignoff,
                                   enableConcurrentRuns: enableConcurrentRuns,
                                   knownValidInputTypes: knownValidInputTypes,
                                   subworkflow: true);
    }

    private InProcessRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? sessionId = null, object? existingOwnerSignoff = null, bool subworkflow = false, bool enableConcurrentRuns = false, IEnumerable<Type>? knownValidInputTypes = null)
    {
        if (enableConcurrentRuns && !workflow.AllowConcurrent)
        {
            throw new InvalidOperationException("Workflow must only consist of cross-run share-capable or factory-created executors. Executors " +
                $"not supporting concurrent: {string.Join(", ", workflow.NonConcurrentExecutorIds)}");
        }

        this.SessionId = sessionId ?? Guid.NewGuid().ToString("N");
        this.StartExecutorId = workflow.StartExecutorId;

        this.Workflow = Throw.IfNull(workflow);
        this.RunContext = new InProcessRunnerContext(workflow, this.SessionId, checkpointingEnabled: checkpointManager != null, this.OutgoingEvents, this.StepTracer, existingOwnerSignoff, subworkflow, enableConcurrentRuns);
        this.CheckpointManager = checkpointManager;

        this._knownValidInputTypes = knownValidInputTypes != null
                                   ? [.. knownValidInputTypes]
                                   : [];

        // Initialize the runners for each of the edges, along with the state for edges that need it.
        this.EdgeMap = new EdgeMap(this.RunContext, this.Workflow.Edges, this.Workflow.Ports.Values, this.Workflow.StartExecutorId, this.StepTracer);
    }

    /// <inheritdoc cref="ISuperStepRunner.SessionId"/>
    public string SessionId { get; }

    /// <inheritdoc cref="ISuperStepRunner.StartExecutorId"/>
    public string StartExecutorId { get; }

    /// <summary>
    /// Gating flag for deferred event republishing after checkpoint restore.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Written with <see cref="Volatile.Write(ref int, int)"/> in <see cref="ResumeStreamAsync(ExecutionMode, CheckpointInfo, bool, CancellationToken)"/>
    /// and consumed atomically with <see cref="Interlocked.Exchange(ref int, int)"/> in
    /// <see cref="ISuperStepRunner.RepublishPendingEventsAsync"/>. The write does not need a full
    /// memory barrier because it is sequenced before the <see cref="AsyncRunHandle"/> constructor
    /// by the <see langword="await"/> in <see cref="ResumeStreamAsync(ExecutionMode, CheckpointInfo, bool, CancellationToken)"/>. The constructor is the
    /// only code path that triggers consumption (via the event stream's subscribe and republish flow).
    /// </para>
    /// <para>
    /// Note: <see cref="AsyncRunHandle"/> also reads <see cref="ISuperStepRunner.HasUnservicedRequests"/>
    /// in its constructor to signal the run loop, but that property reads from
    /// <see cref="InProcessRunnerContext"/>'s request dictionary (restored during
    /// <see cref="RestoreCheckpointCoreAsync"/>), not from this flag. The two are independent:
    /// <c>HasUnservicedRequests</c> triggers the run loop; <c>_needsRepublish</c> triggers event emission.
    /// </para>
    /// </remarks>
    private int _needsRepublish;

    /// <inheritdoc cref="ISuperStepRunner.TelemetryContext"/>
    public WorkflowTelemetryContext TelemetryContext => this.Workflow.TelemetryContext;

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

    public ValueTask<AsyncRunHandle> ResumeStreamAsync(ExecutionMode mode, CheckpointInfo fromCheckpoint, CancellationToken cancellationToken = default)
        => this.ResumeStreamAsync(mode, fromCheckpoint, republishPendingEvents: true, cancellationToken);

    public async ValueTask<AsyncRunHandle> ResumeStreamAsync(ExecutionMode mode, CheckpointInfo fromCheckpoint, bool republishPendingEvents, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(fromCheckpoint);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This runner was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        // Restore checkpoint state without republishing pending request events.
        // The event stream will republish them after subscribing so that events
        // are never lost to an absent subscriber.
        await this.RestoreCheckpointCoreAsync(fromCheckpoint, cancellationToken).ConfigureAwait(false);

        if (republishPendingEvents)
        {
            // Signal the event stream to republish pending requests after subscribing.
            // This is consumed atomically by RepublishPendingEventsAsync.
            Volatile.Write(ref this._needsRepublish, 1);
        }

        return new AsyncRunHandle(this, this, mode);
    }

    bool ISuperStepRunner.HasUnservicedRequests => this.RunContext.HasUnservicedRequests;
    bool ISuperStepRunner.HasUnprocessedMessages => this.RunContext.NextStepHasActions;
    bool ISuperStepRunner.TryGetResponsePortExecutorId(string portId, out string? executorId)
        => this.RunContext.TryGetResponsePortExecutorId(portId, out executorId);

    ValueTask ISuperStepRunner.RepublishPendingEventsAsync(CancellationToken cancellationToken)
    {
        if (Interlocked.Exchange(ref this._needsRepublish, 0) != 0)
        {
            return this.RunContext.RepublishUnservicedRequestsAsync(cancellationToken);
        }

        return default;
    }

    public bool IsCheckpointingEnabled => this.RunContext.IsCheckpointingEnabled;

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

        // TODO: #5084 - Add delivery-level activity (max one per step per executor) to capture non-message
        // specific invocations of executor logic.
        IWorkflowContext tracelessContext = this.RunContext.BindWorkflowContext(receiverId);

        try
        {
            await executor.OnMessageDeliveryStartingAsync(tracelessContext, cancellationToken)
                          .ConfigureAwait(false);

            while (envelopes.TryDequeue(out var envelope))
            {
                (object message, TypeId messageType) = await TranslateMessageAsync(envelope).ConfigureAwait(false);

                await executor.ExecuteCoreAsync(
                    message,
                    messageType,
                    this.RunContext.BindWorkflowContext(receiverId, envelope.TraceContext),
                    this.TelemetryContext,
                    cancellationToken
                ).ConfigureAwait(false);
            }
        }
        finally
        {
            await executor.OnMessageDeliveryFinishedAsync(tracelessContext, cancellationToken)
                          .ConfigureAwait(false);
        }

        async ValueTask<(object, TypeId)> TranslateMessageAsync(MessageEnvelope envelope)
        {
            object? value = envelope.Message;
            TypeId messageType = envelope.MessageType;

            if (!envelope.IsExternal)
            {
                Executor source = await this.RunContext.EnsureExecutorAsync(envelope.SourceId, this.StepTracer, cancellationToken).ConfigureAwait(false);
                Type? actualType = source.Protocol.SendTypeTranslator.MapTypeId(envelope.MessageType);
                if (actualType == null)
                {
                    // In principle, this should never happen, since we always use the SendTypeTranslator to generate the outgoing TypeId in the first place.
                    throw new InvalidOperationException($"Cannot translate message type ID '{envelope.MessageType}' from executor '{source.Id}'.");
                }

                messageType = new(actualType);

                if (value is PortableValue portableValue &&
                    !portableValue.IsType(actualType, out value))
                {
                    throw new InvalidOperationException($"Cannot interpret incoming message of type '{portableValue.TypeId}' as type '{actualType.FullName}'.");
                }
            }

            return (value, messageType);
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
        List<Task> subworkflowTasks = [];
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
    private CheckpointInfo? _lastCheckpointInfo;
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

        Checkpoint checkpoint = new(this.StepTracer.StepNumber, this._workflowInfoCache, runnerData, stateData, edgeData, this._lastCheckpointInfo);
        this._lastCheckpointInfo = await this.CheckpointManager.CommitCheckpointAsync(this.SessionId, checkpoint).ConfigureAwait(false);
        this.StepTracer.TraceCheckpointCreated(this._lastCheckpointInfo);
        this._checkpoints.Add(this._lastCheckpointInfo);
    }

    /// <summary>
    /// Restores checkpoint state and re-emits any pending external request events.
    /// </summary>
    /// <remarks>
    /// This is the <see cref="ICheckpointingHandle"/> implementation used for runtime restores
    /// where the event stream subscription is already active. For initial resumes,
    /// <see cref="ResumeStreamAsync(ExecutionMode, CheckpointInfo, CancellationToken)"/> calls
    /// <see cref="RestoreCheckpointCoreAsync"/> directly and defers republishing to the event stream.
    /// </remarks>
    public async ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
    {
        await this.RestoreCheckpointCoreAsync(checkpointInfo, cancellationToken).ConfigureAwait(false);

        // Republish pending request events. This is safe for runtime restores where
        // the event stream is already subscribed. For initial resumes the event stream
        // handles republishing itself, so ResumeStreamAsync calls RestoreCheckpointCoreAsync directly.
        await this.RunContext.RepublishUnservicedRequestsAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Restores checkpoint state (queued messages, executor state, edge state, etc.)
    /// without republishing pending request events. The caller is responsible for
    /// ensuring events are republished after an event subscriber is attached.
    /// </summary>
    private async ValueTask RestoreCheckpointCoreAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
    {
        this.RunContext.CheckEnded();
        Throw.IfNull(checkpointInfo);
        if (this.CheckpointManager is null)
        {
            throw new InvalidOperationException("This run was not configured with a CheckpointManager, so it cannot restore checkpoints.");
        }

        Checkpoint checkpoint = await this.CheckpointManager.LookupCheckpointAsync(this.SessionId, checkpointInfo)
                                                            .ConfigureAwait(false);

        // Validate the checkpoint is compatible with this workflow
        if (!this.CheckWorkflowMatch(checkpoint))
        {
            // TODO: ArgumentException?
            throw new InvalidDataException("The specified checkpoint is not compatible with the workflow associated with this runner.");
        }

        ValueTask restoreCheckpointIndexTask = UpdateCheckpointIndexAsync();

        await this.RunContext.StateManager.ImportStateAsync(checkpoint).ConfigureAwait(false);
        await this.RunContext.ImportStateAsync(checkpoint).ConfigureAwait(false);

        Task executorNotifyTask = this.RunContext.NotifyCheckpointLoadedAsync(cancellationToken);

        await this.EdgeMap.ImportStateAsync(checkpoint).ConfigureAwait(false);
        await Task.WhenAll(executorNotifyTask,
                           restoreCheckpointIndexTask.AsTask()).ConfigureAwait(false);

        this._lastCheckpointInfo = checkpointInfo;
        this.StepTracer.Reload(this.StepTracer.StepNumber);

        async ValueTask UpdateCheckpointIndexAsync()
        {
            this._checkpoints.Clear();
            this._checkpoints.AddRange(await this.CheckpointManager!.RetrieveIndexAsync(this.SessionId).ConfigureAwait(false));
        }
    }

    private bool CheckWorkflowMatch(Checkpoint checkpoint) =>
        checkpoint.Workflow.IsMatch(this.Workflow);

    public ValueTask RequestEndRunAsync() => this.RunContext.EndRunAsync();
}
