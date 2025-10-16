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
        var runHandle = await this.GetRunHandleWithTurnTokenAsync(workflow: workflow, input: input, checkpointManager: null, runId: runId, cancellationToken).ConfigureAwait(false);

        Run run = new(runHandle);
        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return run;
    }

    /// <inheritdoc/>
    public async ValueTask<Run> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        var runHandle = await this.GetRunHandleWithTurnTokenAsync(workflow: workflow, input: input, checkpointManager: null, runId: runId, cancellationToken).ConfigureAwait(false);

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
        var runHandle = await this.GetRunHandleWithTurnTokenAsync(workflow: workflow, input: input, checkpointManager: checkpointManager, runId: runId, cancellationToken).ConfigureAwait(false);

        Run run = new(runHandle);
        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return await runHandle.WithCheckpointingAsync(() => new ValueTask<Run>(run))
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
        var runHandle = await this.GetRunHandleWithTurnTokenAsync(workflow: workflow, input: input, checkpointManager: checkpointManager, runId: runId, cancellationToken).ConfigureAwait(false);

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

    // Helper to construct a RunHandle with the provided input enqueued. If the starting executor supports it, a TurnToken will be enqueued also.
    private async ValueTask<AsyncRunHandle> GetRunHandleWithTurnTokenAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager? checkpointManager,
        string? runId,
        CancellationToken cancellationToken)
    {
        var knownTypes = new List<Type>() { typeof(TInput) };
        var needsTurnToken = await StartingExecutorHandlesTurnTokenAsync<TInput>(workflow).ConfigureAwait(false);
        if (needsTurnToken)
        {
            knownTypes.Add(typeof(TurnToken));
        }

        AsyncRunHandle runHandle = await this.BeginRunAsync(workflow, checkpointManager: checkpointManager, runId: runId, knownTypes, cancellationToken)
                                             .ConfigureAwait(false);

        await runHandle.EnqueueMessageAsync(input, cancellationToken).ConfigureAwait(false);

        if (needsTurnToken)
        {
            await runHandle.EnqueueMessageAsync(new TurnToken(emitEvents: true), cancellationToken).ConfigureAwait(false);
        }

        return runHandle;
    }

    /// <summary>
    /// Helper method to detect if the starting executor of a given workflow accepts the provided input type as well as a TurnToken.
    /// </summary>
    private static async ValueTask<bool> StartingExecutorHandlesTurnTokenAsync<TInput>(Workflow workflow)
    {
        if (workflow.Registrations.TryGetValue(workflow.StartExecutorId, out var registration))
        {
            // Create instance to check type
            Executor startExecutor = await registration.CreateInstanceAsync(string.Empty)
                                                       .ConfigureAwait(false);
            return startExecutor.CanHandle(typeof(TInput)) && startExecutor.CanHandle(typeof(TurnToken));
        }

        return false;
    }
}
