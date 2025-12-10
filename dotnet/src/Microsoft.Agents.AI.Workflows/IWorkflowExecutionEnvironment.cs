// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Defines an execution environment for running, streaming, and resuming workflows asynchronously, with optional
/// checkpointing and run management capabilities.
/// </summary>
public interface IWorkflowExecutionEnvironment
{
    /// <summary>
    /// Initiates a streaming run of the specified workflow without sending any initial input. Note that the starting
    /// <see cref="Executor"/> will not be invoked until an input message is received.
    /// </summary>
    /// <param name="workflow">The workflow to execute. Cannot be null.</param>
    /// <param name="runId">An optional identifier for the run. If null, a new run identifier will be generated.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the streaming operation.</param>
    /// <returns>A ValueTask that represents the asynchronous operation. The result contains a StreamingRun object for accessing
    /// the streamed workflow output.</returns>
    ValueTask<StreamingRun> OpenStreamAsync(Workflow workflow, string? runId = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Initiates an asynchronous streaming execution using the specified input.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun"/> provides methods to observe and control
    /// the ongoing streaming execution. The operation will continue until the streaming execution is finished or
    /// cancelled.</remarks>
    /// <typeparam name="TInput">A type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the streaming run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    ValueTask<StreamingRun> StreamAsync<TInput>(Workflow workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull;

    /// <summary>
    /// Initiates an asynchronous streaming execution without sending any initial input, with checkpointing.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun"/> provides methods to observe and control
    /// the ongoing streaming execution. The operation will continue until the streaming execution is finished or
    /// cancelled.</remarks>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    ValueTask<Checkpointed<StreamingRun>> StreamAsync(Workflow workflow, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Initiates an asynchronous streaming execution using the specified input, with checkpointing.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun"/> provides methods to observe and control
    /// the ongoing streaming execution. The operation will continue until the streaming execution is finished or
    /// cancelled.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the streaming run.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull;

    /// <summary>
    /// Resumes an asynchronous streaming execution for the specified input from a checkpoint.
    /// </summary>
    /// <remarks>If the operation is cancelled via the <paramref name="cancellationToken"/> token, the streaming execution will
    /// be terminated.</remarks>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="StreamingRun"/> that provides access to the results of the streaming run.</returns>
    ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    ValueTask<Run> RunAsync<TInput>(Workflow workflow, TInput input, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull;

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input, with checkpointing.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    ValueTask<Checkpointed<Run>> RunAsync<TInput>(Workflow workflow, TInput input, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default) where TInput : notnull;

    /// <summary>
    /// Resumes a non-streaming execution of the workflow from a checkpoint.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    ValueTask<Checkpointed<Run>> ResumeAsync(Workflow workflow, CheckpointInfo fromCheckpoint, CheckpointManager checkpointManager, string? runId = null, CancellationToken cancellationToken = default);
}
