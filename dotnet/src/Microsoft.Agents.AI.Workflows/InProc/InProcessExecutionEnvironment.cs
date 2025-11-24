// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.InProc;

/// <summary>
/// Provides an in-process implementation of the workflow execution environment for running, streaming, and
/// checkpointing workflows within the current application domain.
/// </summary>
public sealed class InProcessExecutionEnvironment : IWorkflowExecutionEnvironment
{
    internal InProcessExecutionEnvironment(ExecutionMode mode, bool enableConcurrentRuns = false)
    {
        this.ExecutionMode = mode;
        this.EnableConcurrentRuns = enableConcurrentRuns;
    }

    internal ExecutionMode ExecutionMode { get; }
    internal bool EnableConcurrentRuns { get; }

    internal ValueTask<AsyncRunHandle> BeginRunAsync(Workflow workflow, ICheckpointManager? checkpointManager, string? runId, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager, runId, this.EnableConcurrentRuns, knownValidInputTypes);
        return runner.BeginStreamAsync(this.ExecutionMode, cancellationToken);
    }

    internal ValueTask<AsyncRunHandle> ResumeRunAsync(Workflow workflow, ICheckpointManager? checkpointManager, string? runId, CheckpointInfo fromCheckpoint, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = InProcessRunner.CreateTopLevelRunner(workflow, checkpointManager, runId, this.EnableConcurrentRuns, knownValidInputTypes);
        return runner.ResumeStreamAsync(this.ExecutionMode, fromCheckpoint, cancellationToken);
    }

    /// <inheritdoc/>
    public async ValueTask<StreamingRun> OpenStreamAsync(
        Workflow workflow,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: null, runId: runId, [], cancellationToken)
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
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: null, runId: runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.EnqueueAndStreamAsync(input, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<StreamingRun>> StreamAsync(
        Workflow workflow,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId: runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync<StreamingRun>(() => new(new StreamingRun(runHandle)))
                              .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId: runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync(() => runHandle.EnqueueAndStreamAsync(input, cancellationToken))
                              .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, checkpointManager, runId: runId, fromCheckpoint, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync<StreamingRun>(() => new(new StreamingRun(runHandle)))
                              .ConfigureAwait(false);
    }

    private async ValueTask<AsyncRunHandle> BeginRunHandlingChatProtocolAsync<TInput>(Workflow workflow,
        TInput input,
        CheckpointManager? checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        ProtocolDescriptor descriptor = await workflow.DescribeProtocolAsync(cancellationToken).ConfigureAwait(false);
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId, descriptor.Accepts, cancellationToken)
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
                                                checkpointManager: null,
                                                runId,
                                                cancellationToken)
                                             .ConfigureAwait(false);

        Run run = new(runHandle);
        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return run;
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunHandlingChatProtocolAsync(
                                                workflow,
                                                input,
                                                checkpointManager,
                                                runId,
                                                cancellationToken)
                                             .ConfigureAwait(false);

        Run run = new(runHandle);
        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return await runHandle.WithCheckpointingAsync(() => new ValueTask<Run>(run))
                              .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<Run>> ResumeAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, checkpointManager, runId: runId, fromCheckpoint, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync<Run>(() => new(new Run(runHandle)))
                              .ConfigureAwait(false);
    }
}
