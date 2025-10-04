// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal class WorkflowHostExecutor : Executor, IResettableExecutor
{
    private readonly string _runId;
    private readonly Workflow _workflow;
    private readonly object _ownershipToken;

    private InProcessRunner? _activeRunner;
    private InMemoryCheckpointManager? _checkpointManager;
    private readonly ExecutorOptions _options;

    private ISuperStepJoinContext? _joinContext;
    private StreamingRun? _run;

    [MemberNotNullWhen(true, nameof(_checkpointManager))]
    private bool WithCheckpointing => this._checkpointManager != null;

    public WorkflowHostExecutor(string id, Workflow workflow, string runId, object ownershipToken, ExecutorOptions? options = null) : base(id, options)
    {
        this._options = options ?? new();

        Throw.IfNull(workflow);
        this._runId = Throw.IfNull(runId);
        this._ownershipToken = Throw.IfNull(ownershipToken);
        this._workflow = Throw.IfNull(workflow);
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.AddCatchAll(this.QueueExternalMessageAsync);
    }

    private async ValueTask QueueExternalMessageAsync(PortableValue portableValue, IWorkflowContext context)
    {
        if (portableValue.Is(out ExternalResponse? response))
        {
            response = this.CheckAndUnqualifyResponse(response);
            await this.EnsureRunSendMessageAsync(response).ConfigureAwait(false);
        }
        else
        {
            InProcessRunner runner = await this.EnsureRunnerAsync().ConfigureAwait(false);
            IEnumerable<Type> validInputTypes = await runner.RunContext.GetStartingExecutorInputTypesAsync().ConfigureAwait(false);
            foreach (Type candidateType in validInputTypes)
            {
                if (portableValue.IsType(candidateType, out object? message))
                {
                    await this.EnsureRunSendMessageAsync(message, candidateType).ConfigureAwait(false);
                    return;
                }
            }
        }
    }

    private ISuperStepJoinContext JoinContext => Throw.IfNull(this._joinContext, "Must attach to a join context before starting the run.");

    internal async ValueTask<InProcessRunner> EnsureRunnerAsync()
    {
        if (this._activeRunner == null)
        {
            if (this.JoinContext.WithCheckpointing)
            {
                // Use a seprate in-memory checkpoint manager for scoping purposes. We do not need to worry about
                // serialization because we will be relying on the parent workflow's checkpoint manager to do that,
                // if needed. For our purposes, all we need is to keep a faithful representation of the checkpointed
                // objects so we can emit them back to the parent workflow on checkpoint creation.
                this._checkpointManager = new InMemoryCheckpointManager();
            }

            this._activeRunner = new(this._workflow, this._checkpointManager, this._runId, this._ownershipToken, subworkflow: true);
        }

        return this._activeRunner;
    }

    internal async ValueTask<StreamingRun> EnsureRunSendMessageAsync(object? incomingMessage = null, Type? incomingMessageType = null, bool resume = false, CancellationToken cancellation = default)
    {
        Debug.Assert(this._joinContext != null, "Must attach to a join context before starting the run.");

        if (this._run != null)
        {
            if (incomingMessage != null)
            {
                await this._run.TrySendMessageUntypedAsync(incomingMessage, incomingMessageType ?? incomingMessage.GetType()).ConfigureAwait(false);
            }

            return this._run;
        }

        InProcessRunner activeRunner = await this.EnsureRunnerAsync().ConfigureAwait(false);
        AsyncRunHandle runHandle;

        if (this.WithCheckpointing)
        {
            if (resume)
            {
                // Attempting to resume from checkpoint
                if (!this._checkpointManager.TryGetLastCheckpoint(this._runId, out CheckpointInfo? lastCheckpoint))
                {
                    throw new InvalidOperationException("No checkpoints available to resume from.");
                }

                runHandle = await activeRunner.ResumeStreamAsync(InProcessExecution.DefaultMode, lastCheckpoint!, cancellation)
                                                             .ConfigureAwait(false);
                if (incomingMessage != null)
                {
                    await runHandle.EnqueueUntypedAndRunAsync(incomingMessage, cancellation).ConfigureAwait(false);
                }
            }
            else if (incomingMessage != null)
            {
                runHandle = await activeRunner.BeginStreamAsync(InProcessExecution.DefaultMode, cancellation)
                                                             .ConfigureAwait(false);

                await runHandle.EnqueueUntypedAndRunAsync(incomingMessage, cancellation).ConfigureAwait(false);
            }
            else
            {
                throw new InvalidOperationException("Cannot start a checkpointed workflow run without an incoming message or resume flag.");
            }
        }
        else
        {
            runHandle = await activeRunner.BeginStreamAsync(InProcessExecution.DefaultMode, cancellation).ConfigureAwait(false);

            await runHandle.EnqueueMessageUntypedAsync(Throw.IfNull(incomingMessage), cancellation: cancellation).ConfigureAwait(false);
        }

        this._run = new(runHandle);

        await this._joinContext.AttachSuperstepAsync(activeRunner, cancellation).ConfigureAwait(false);
        activeRunner.OutgoingEvents.EventRaised += this.ForwardWorkflowEventAsync;

        return this._run;
    }

    private ExternalResponse? CheckAndUnqualifyResponse([DisallowNull] ExternalResponse response)
    {
        if (!Throw.IfNull(response).PortInfo.PortId.StartsWith($"{this.Id}.", StringComparison.Ordinal))
        {
            return null;
        }

        RequestPortInfo unqualifiedPort = response.PortInfo with { PortId = response.PortInfo.PortId.Substring(this.Id.Length + 1) };
        return response with { PortInfo = unqualifiedPort };
    }

    private ExternalRequest QualifyRequestPortId(ExternalRequest internalRequest)
    {
        RequestPortInfo requestPort = internalRequest.PortInfo with { PortId = $"{this.Id}.{internalRequest.PortInfo.PortId}" };
        return internalRequest with { PortInfo = requestPort };
    }

    private async ValueTask ForwardWorkflowEventAsync(object? sender, WorkflowEvent evt)
    {
        // Note that we are explicitly not using the checked JoinContext property here, because this is an async callback.
        try
        {
            Task resultTask = Task.CompletedTask;
            switch (evt)
            {
                case WorkflowStartedEvent:
                case SuperStepStartedEvent:
                case SuperStepCompletedEvent:
                    // These events are internal to the subworkflow and do not need to be forwarded.
                    break;
                case RequestInfoEvent requestInfoEvt:
                    ExternalRequest request = requestInfoEvt.Request;
                    resultTask = this._joinContext?.SendMessageAsync(this.Id, this.QualifyRequestPortId(request)).AsTask() ?? Task.CompletedTask;
                    break;
                case WorkflowErrorEvent errorEvent:
                    resultTask = this._joinContext?.ForwardWorkflowEventAsync(new SubworkflowErrorEvent(this.Id, errorEvent.Data as Exception)).AsTask() ?? Task.CompletedTask;
                    break;
                case WorkflowOutputEvent outputEvent:
                    if (this._joinContext != null &&
                        this._options.AutoSendMessageHandlerResultObject
                        && outputEvent.Data != null)
                    {
                        resultTask = this._joinContext.SendMessageAsync(this.Id, outputEvent.Data).AsTask();
                    }
                    break;
                case RequestHaltEvent requestHaltEvent:
                    resultTask = this._joinContext?.ForwardWorkflowEventAsync(new RequestHaltEvent()).AsTask() ?? Task.CompletedTask;
                    break;
                case WorkflowWarningEvent warningEvent:
                    if (warningEvent.Data is string warningMessage)
                    {
                        resultTask = this._joinContext?.ForwardWorkflowEventAsync(new SubworkflowWarningEvent(this.Id, warningMessage)).AsTask() ?? Task.CompletedTask;
                    }
                    break;
                default:
                    resultTask = this._joinContext?.ForwardWorkflowEventAsync(evt).AsTask() ?? Task.CompletedTask;
                    break;
            }

            await resultTask.ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            try
            {
                _ = this._joinContext?.ForwardWorkflowEventAsync(new SubworkflowErrorEvent(this.Id, ex)).AsTask();
            }
            catch
            { }
        }
    }

    internal async ValueTask AttachSuperStepContextAsync(ISuperStepJoinContext joinContext)
    {
        this._joinContext = Throw.IfNull(joinContext);
    }

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await context.QueueStateUpdateAsync(nameof(CheckpointManager), this._checkpointManager).ConfigureAwait(false);

        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        InMemoryCheckpointManager manager = await context.ReadStateAsync<InMemoryCheckpointManager>(nameof(InMemoryCheckpointManager)).ConfigureAwait(false) ?? new();
        if (this._checkpointManager == manager)
        {
            // We are restoring in the context of the same run; not need to rebuild the entire execution stack.
        }
        else
        {
            this._checkpointManager = manager;

            await this.ResetAsync().ConfigureAwait(false);
        }

        StreamingRun run = await this.EnsureRunSendMessageAsync(cancellation: cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask ResetAsync()
    {
        this._run = null;

        if (this._activeRunner != null)
        {
            this._activeRunner.OutgoingEvents.EventRaised -= this.ForwardWorkflowEventAsync;
            await this._activeRunner.RequestEndRunAsync().ConfigureAwait(false);

            this._activeRunner = new(this._workflow, this._checkpointManager, this._runId);
        }
    }
}
