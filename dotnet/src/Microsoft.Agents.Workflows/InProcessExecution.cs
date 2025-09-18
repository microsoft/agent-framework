// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.InProc;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides methods to initiate and manage in-process workflow executions, supporting both streaming and
/// non-streaming modes with asynchronous operations.
/// </summary>
public static class InProcessExecution
{
    /// <summary>
    /// Initiates an asynchronous streaming execution using the specified input.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun"/> provides methods to observe and control
    /// the ongoing streaming execution. The operation will continue until the streaming execution is finished or
    /// cancelled.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the streaming run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<StreamingRun> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager: null);
        return runner.StreamAsync(input, cancellation);
    }

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
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    public static async ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager);
        StreamingRun result = await runner.StreamAsync(input, cancellation).ConfigureAwait(false);

        await runner.CheckpointAsync(cancellation).ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Resumes an asynchronous streaming execution for the specified input from a checkpoint.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun{TResult}"/> can be used to retrieve results
    /// as they become available. If the operation is cancelled via the <paramref name="cancellation"/> token, the
    /// streaming execution will be terminated.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="StreamingRun{TResult}"/> that provides access to the results of the streaming
    /// run.</returns>
    public static async ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager, runId: fromCheckpoint.RunId);
        StreamingRun result = await runner.ResumeStreamAsync(fromCheckpoint, cancellation).ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Initiates an asynchronous streaming execution for the specified input.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun{TResult}"/> can be used to retrieve results
    /// as they become available. If the operation is cancelled via the <paramref name="cancellation"/> token, the
    /// streaming execution will be terminated.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input value to be processed by the streaming run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="StreamingRun{TResult}"/> that provides access to the results of the streaming
    /// run.</returns>
    public static ValueTask<StreamingRun<TResult>> StreamAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        TInput input,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager: null);
        return runner.StreamAsync(input, cancellation);
    }

    /// <summary>
    /// Initiates an asynchronous streaming execution for the specified input, with checkpointing.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun{TResult}"/> can be used to retrieve results
    /// as they become available. If the operation is cancelled via the <paramref name="cancellation"/> token, the
    /// streaming execution will be terminated.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input value to be processed by the streaming run.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="StreamingRun{TResult}"/> that provides access to the results of the streaming
    /// run.</returns>
    public static async ValueTask<Checkpointed<StreamingRun<TResult>>> StreamAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager);
        StreamingRun<TResult> result = await runner.StreamAsync(input, cancellation).ConfigureAwait(false);

        await runner.CheckpointAsync().ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Resumes an asynchronous streaming execution of the workflow from a checkpoint.
    /// </summary>
    /// <remarks>The returned <see cref="StreamingRun{TResult}"/> can be used to retrieve results
    /// as they become available. If the operation is cancelled via the <paramref name="cancellation"/> token, the
    /// streaming execution will be terminated.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="StreamingRun{TResult}"/> that provides access to the results of the streaming
    /// run.</returns>
    public static async ValueTask<Checkpointed<StreamingRun<TResult>>> ResumeStreamAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager, runId: fromCheckpoint.RunId);
        StreamingRun<TResult> result = await runner.ResumeStreamAsync(fromCheckpoint, cancellation).ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Run> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager: null);
        return runner.RunAsync(input, cancellation);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input, with checkpointing.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static async ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager);
        Run result = await runner.RunAsync(input, cancellation).ConfigureAwait(false);

        await runner.CheckpointAsync(cancellation).ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Resumes a non-streaming execution of the workflow from a checkpoint.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static async ValueTask<Checkpointed<Run>> ResumeAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow, checkpointManager, runId: fromCheckpoint.RunId);
        Run result = await runner.ResumeAsync(fromCheckpoint, cancellation).ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Run<TResult>> RunAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        TInput input,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager: null);
        return runner.RunAsync(input, cancellation);
    }

    /// <summary>
    /// Initiates a non-streaming execution of the workflow with the specified input, with checkpointing.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="input">The input message to be processed as part of the run.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static async ValueTask<Checkpointed<Run<TResult>>> RunAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager);
        Run<TResult> result = await runner.RunAsync(input, cancellation).ConfigureAwait(false);

        await runner.CheckpointAsync().ConfigureAwait(false);

        return new(result, runner);
    }

    /// <summary>
    /// Resumes a non-streaming execution of the workflow from a checkpoint.
    /// </summary>
    /// <remarks>The workflow will run until its first halt, and the returned <see cref="Run"/> will capture
    /// all outgoing events. Use the <c>Run</c> instance to resume execution with responses to outgoing events.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <typeparam name="TResult">The type of output produced by the workflow.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static async ValueTask<Checkpointed<Run<TResult>>> ResumeAsync<TInput, TResult>(
        Workflow<TInput, TResult> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow, checkpointManager, runId: fromCheckpoint.RunId);
        Run<TResult> result = await runner.ResumeAsync(fromCheckpoint, cancellation).ConfigureAwait(false);

        return new(result, runner);
    }
}
