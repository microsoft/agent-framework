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
    private readonly ExecutionMode _executionMode;
    internal InProcessExecutionEnvironment(ExecutionMode mode)
    {
        this._executionMode = mode;
    }

    internal ValueTask<AsyncRunHandle> BeginRunAsync(Workflow workflow, ICheckpointManager? checkpointManager, string? runId, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = new(workflow, checkpointManager, runId, knownValidInputTypes: knownValidInputTypes);
        return runner.BeginStreamAsync(this._executionMode, cancellationToken);
    }

    internal ValueTask<AsyncRunHandle> ResumeRunAsync(Workflow workflow, ICheckpointManager? checkpointManager, string? runId, CheckpointInfo fromCheckpoint, IEnumerable<Type> knownValidInputTypes, CancellationToken cancellationToken)
    {
        InProcessRunner runner = new(workflow, checkpointManager, runId, knownValidInputTypes: knownValidInputTypes);
        return runner.ResumeStreamAsync(this._executionMode, fromCheckpoint, cancellationToken);
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
    public async ValueTask<StreamingRun> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: null, runId: runId, [typeof(TInput)], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.EnqueueAndStreamAsync(input, cancellationToken).ConfigureAwait(false);
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
    public async ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId: runId, [typeof(TInput)], cancellationToken)
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

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, checkpointManager, runId: runId, fromCheckpoint, [typeof(TInput)], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync<StreamingRun>(() => new(new StreamingRun(runHandle)))
                              .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Run> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: null, runId: runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.EnqueueAndRunAsync(input, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Run> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: null, runId: runId, [typeof(TInput)], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.EnqueueAndRunAsync(input, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId: runId, [], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync(() => runHandle.EnqueueAndRunAsync(input, cancellationToken))
                              .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager, runId: runId, [typeof(TInput)], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync(() => runHandle.EnqueueAndRunAsync(input, cancellationToken))
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

    /// <inheritdoc/>
    public async ValueTask<Checkpointed<Run>> ResumeAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        AsyncRunHandle runHandle = await this.ResumeRunAsync(workflow, checkpointManager, runId: runId, fromCheckpoint, [typeof(TInput)], cancellationToken)
                                             .ConfigureAwait(false);

        return await runHandle.WithCheckpointingAsync<Run>(() => new(new Run(runHandle)))
                              .ConfigureAwait(false);
    }
}
