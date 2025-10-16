// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides methods to initiate and manage in-process workflow executions, supporting both streaming and
/// non-streaming modes with asynchronous operations.
/// </summary>
public static class InProcessExecution
{
    /// <summary>
    /// The default InProcess execution environment.
    /// </summary>
    public static InProcessExecutionEnvironment Default => OffThread;

    /// <summary>
    /// An InProcessExecution environment which will run SuperSteps in a background thread, streaming
    /// events out as they are raised.
    /// </summary>
    public static InProcessExecutionEnvironment OffThread { get; } = new(ExecutionMode.OffThread);

    /// <summary>
    /// Gets an execution environment that enables concurrent, off-thread in-process execution.
    /// </summary>
    public static InProcessExecutionEnvironment Concurrent { get; } = new(ExecutionMode.OffThread, enableConcurrentRuns: true);

    /// <summary>
    /// An InProcesExecution environment which will run SuperSteps in the event watching thread,
    /// accumulating events during each SuperStep and streaming them out after each SuperStep is
    /// completed.
    /// </summary>
    public static InProcessExecutionEnvironment Lockstep { get; } = new(ExecutionMode.Lockstep);

    /// <summary>
    /// An InProcessExecution environment which will not run SuperSteps directly, relying instead
    /// on the hosting workflow to run them directly, while streaming events out as they are raised.
    /// </summary>
    internal static InProcessExecutionEnvironment Subworkflow { get; } = new(ExecutionMode.Subworkflow);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.StreamAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> StreamAsync<TInput>(Workflow workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.StreamAsync(workflow, input, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.StreamAsync{TInput}(Workflow{TInput}, TInput, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> StreamAsync<TInput>(Workflow<TInput> workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.StreamAsync(workflow, input, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.StreamAsync{TInput}(Workflow, TInput, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.StreamAsync(workflow, input, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.StreamAsync{TInput}(Workflow{TInput}, TInput, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(Workflow<TInput> workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.StreamAsync(workflow, input, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeStreamAsync(Workflow, CheckpointInfo, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default)
        => Default.ResumeStreamAsync(workflow, fromCheckpoint, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeStreamAsync{TInput}(Workflow{TInput}, CheckpointInfo, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync<TInput>(Workflow<TInput> workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.ResumeStreamAsync(workflow, fromCheckpoint, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<Run> RunAsync<TInput>(Workflow workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunAsync(workflow, input, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow{TInput}, TInput, string?, CancellationToken)"/>
    public static ValueTask<Run> RunAsync<TInput>(Workflow<TInput> workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunAsync(workflow, input, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow, TInput, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<Run>> RunAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunAsync(workflow, input, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow{TInput}, TInput, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<Run>> RunAsync<TInput>(Workflow<TInput> workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunAsync(workflow, input, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeAsync(Workflow, CheckpointInfo, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<Run>> ResumeAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default)
        => Default.ResumeAsync(workflow, fromCheckpoint, checkpointManager, runId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeAsync{TInput}(Workflow{TInput}, CheckpointInfo, CheckpointManager, string?, CancellationToken)"/>
    public static ValueTask<Checkpointed<Run>> ResumeAsync<TInput>(Workflow<TInput> workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.ResumeAsync(workflow, fromCheckpoint, checkpointManager, runId, cancellationToken);
}
