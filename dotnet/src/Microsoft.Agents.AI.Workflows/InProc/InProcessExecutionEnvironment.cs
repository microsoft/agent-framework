// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.InProc;

/// <summary>
/// Provides an in-process implementation of the workflow execution environment for running, streaming, and
/// checkpointing workflows within the current application domain.
/// </summary>
public sealed class InProcessExecutionEnvironment : IWorkflowExecutionEnvironment
{
    internal InProcessExecutionEnvironment(ExecutionMode mode, bool enableConcurrentRuns = false, CheckpointManager? checkpointManager = null)
    {
        this.ExecutionMode = mode;
        this.EnableConcurrentRuns = enableConcurrentRuns;

        this.CheckpointManager = checkpointManager;
    }

    /// <summary>
    /// Configure a new execution environment, inheriting configuration for the current one with the specified <see cref="Workflows.CheckpointManager"/>
    /// for use in checkpointing.
    /// </summary>
    /// <param name="checkpointManager">The CheckpointManager to use for checkpointing.</param>
    /// <returns>
    /// A new InProcess <see cref="IWorkflowExecutionEnvironment"/> configured for checkpointing, inheriting configuration from the current
    /// environment.
    /// </returns>
    public InProcessExecutionEnvironment WithCheckpointing(CheckpointManager? checkpointManager)
    {
        return new(this.ExecutionMode, this.EnableConcurrentRuns, checkpointManager);
    }

    internal ExecutionMode ExecutionMode { get; }
    internal bool EnableConcurrentRuns { get; }
    internal CheckpointManager? CheckpointManager { get; }

    /// <inheritdoc/>
    public bool IsCheckpointingEnabled => this.CheckpointManager != null;

    internal ValueTask<AsyncRunHandle> BeginRunAsync(Workflow workflow, string? runId, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, this.CheckpointManager, runId, this.EnableConcurrentRuns, knownValidInputTypes);
        return runner.BeginStreamAsync(this.ExecutionMode, cancellationToken);
    }

    internal ValueTask<AsyncRunHandle> ResumeRunAsync(Workflow workflow, CheckpointInfo fromCheckpoint, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, this.CheckpointManager, fromCheckpoint.RunId, this.EnableConcurrentRuns, knownValidInputTypes);
        return runner.ResumeStreamAsync(this.ExecutionMode, fromCheckpoint, cancellationToken);
    }

    /// <inheritdoc/>
    public async ValueTask<StreamingRun> OpenStreamAsync(
        Workflow workflow,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return new(runHandle);
    }

    /// <inheritdoc/>
    public async ValueTask<StreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.EnqueueAndStreamAsync(input, cancellationToken).ConfigureAwait(false);
    }

    [MemberNotNull(nameof(CheckpointManager))]
    private void VerifyCheckpointingConfigured()
    {
        if (this.CheckpointManager == null)
        {
            throw new InvalidOperationException("Checkpointing is not configured for this execution environment. Please use the InProcessExecutionEnvironment.WithCheckpointing method to attach a CheckpointManager.");
        }
    }

    /// <inheritdoc/>
    public async ValueTask<StreamingRun> ResumeStreamAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CancellationToken cancellationToken = default)
    {
        this.VerifyCheckpointingConfigured();

        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, fromCheckpoint, [], cancellationToken)
                                             .ConfigureAwait(false);

        return new(runHandle);
    }

    private async ValueTask<AsyncRunHandle> BeginRunHandlingChatProtocolAsync<TInput>(Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        ProtocolDescriptor descriptor = await workflow.DescribeProtocolAsync(cancellationToken).ConfigureAwait(false);
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, runId, descriptor.Accepts, cancellationToken)
                                             .ConfigureAwait(false);

        await runHandle.EnqueueMessageAsync(input, cancellationToken).ConfigureAwait(false);

        if (descriptor.IsChatProtocol() && input is not TurnToken)
        {
            await runHandle.EnqueueMessageAsync(new TurnToken(emitEvents: true), cancellationToken).ConfigureAwait(false);
        }

        return runHandle;
    }

    /// <inheritdoc/>
    public async ValueTask<Run> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunHandlingChatProtocolAsync(
                                                workflow,
                                                input,
                                                runId,
                                                cancellationToken)
                                             .ConfigureAwait(false);

        Run run = new(runHandle);
        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return run;
    }

    /// <inheritdoc/>
    public async ValueTask<Run> ResumeAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CancellationToken cancellationToken = default)
    {
        this.VerifyCheckpointingConfigured();

        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, fromCheckpoint, [], cancellationToken)
                                             .ConfigureAwait(false);

        return new(runHandle);
    }
}
