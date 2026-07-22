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

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.OpenStreamingAsync(Workflow, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> OpenStreamingAsync(Workflow workflow, string? sessionId = null, CancellationToken cancellationToken = default)
        => Default.OpenStreamingAsync(workflow, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunStreamingAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> RunStreamingAsync<TInput>(Workflow workflow, TInput input, string? sessionId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunStreamingAsync(workflow, input, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.OpenStreamingAsync(Workflow, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> OpenStreamingAsync(Workflow workflow, CheckpointManager checkpointManager, string? sessionId = null, CancellationToken cancellationToken = default)
        => Default.WithCheckpointing(checkpointManager).OpenStreamingAsync(workflow, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunStreamingAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<StreamingRun> RunStreamingAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? sessionId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.WithCheckpointing(checkpointManager).RunStreamingAsync(workflow, input, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeStreamingAsync(Workflow, CheckpointInfo, CancellationToken)"/>
    public static ValueTask<StreamingRun> ResumeStreamingAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, CancellationToken cancellationToken = default)
        => Default.WithCheckpointing(checkpointManager).ResumeStreamingAsync(workflow, fromCheckpoint, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<Run> RunAsync<TInput>(Workflow workflow, TInput input, string? sessionId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.RunAsync(workflow, input, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.RunAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/>
    public static ValueTask<Run> RunAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? sessionId = null, CancellationToken cancellationToken = default) where TInput : notnull
        => Default.WithCheckpointing(checkpointManager).RunAsync(workflow, input, sessionId, cancellationToken);

    /// <inheritdoc cref="IWorkflowExecutionEnvironment.ResumeAsync(Workflow, CheckpointInfo, CancellationToken)"/>
    public static ValueTask<Run> ResumeAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, CancellationToken cancellationToken = default)
        => Default.WithCheckpointing(checkpointManager).ResumeAsync(workflow, fromCheckpoint, cancellationToken);
}
