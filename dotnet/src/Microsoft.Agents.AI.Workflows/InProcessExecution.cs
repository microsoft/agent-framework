// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides methods to initiate and manage in-process workflow executions, supporting both streaming and
/// non-streaming modes with asynchronous operations.
/// </summary>
public static class InProcessExecution
{
    internal static InProcessRunner CreateRunner(Workflow workflow, ICheckpointManager? checkpointManager, string? runId)
        => new(workflow, checkpointManager, runId);

    internal static InProcessRunner CreateRunner<TInput>(Workflow<TInput> checkedWorkflow, ICheckpointManager? checkpointManager, string? runId)
        where TInput : notnull
        => new(checkedWorkflow, checkpointManager, runId, knownValidInputTypes: [typeof(TInput)]);

    private static ValueTask<StreamingRun> StreamAsync<TInput>(InProcessRunner runner, TInput input, CancellationToken cancellationToken = default)
        => runner.StreamAsync(input, cancellationToken);

    private static ValueTask<StreamingRun> StreamAsync(InProcessRunner runner, object input, CancellationToken cancellationToken = default)
        => runner.StreamAsync(input, cancellationToken);

    private static ValueTask<Run> RunAsync<TInput>(InProcessRunner runner, TInput input, CancellationToken cancellationToken = default)
        => runner.RunAsync(input, cancellationToken);

    private static ValueTask<Run> RunAsync(InProcessRunner runner, object input, CancellationToken cancellationToken = default)
        => runner.RunAsync(input, cancellationToken);

    private static async ValueTask<Checkpointed<StreamingRun>> StreamCheckpointedAsync<TInput>(InProcessRunner runner, TInput input, CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        StreamingRun run = await StreamAsync(runner, input, cancellationToken).ConfigureAwait(false);
        await runner.CheckpointAsync(cancellationToken).ConfigureAwait(false);

        return new(run, runner);
    }

    private static async ValueTask<Checkpointed<StreamingRun>> StreamCheckpointedAsync(InProcessRunner runner, object input, CancellationToken cancellationToken = default)
    {
        StreamingRun run = await StreamAsync(runner, input, cancellationToken).ConfigureAwait(false);
        await runner.CheckpointAsync(cancellationToken).ConfigureAwait(false);

        return new(run, runner);
    }

    private static async ValueTask<Checkpointed<Run>> RunCheckpointedAsync<TInput>(InProcessRunner runner, TInput input, CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        Run run = await RunAsync(runner, input, cancellationToken).ConfigureAwait(false);
        await runner.CheckpointAsync(cancellationToken).ConfigureAwait(false);

        return new(run, runner);
    }

    private static async ValueTask<Checkpointed<Run>> RunCheckpointedAsync(InProcessRunner runner, object input, CancellationToken cancellationToken = default)
    {
        Run run = await RunAsync(runner, input, cancellationToken).ConfigureAwait(false);
        await runner.CheckpointAsync(cancellationToken).ConfigureAwait(false);

        return new(run, runner);
    }

    private static async ValueTask<Checkpointed<StreamingRun>> ResumeStreamCheckpointedAsync(InProcessRunner runner, CheckpointInfo fromCheckpoint, CancellationToken cancellationToken = default)
    {
        StreamingRun run = await runner.ResumeStreamAsync(fromCheckpoint, cancellationToken).ConfigureAwait(false);
        return new(run, runner);
    }

    private static async ValueTask<Checkpointed<Run>> ResumeRunCheckpointedAsync(InProcessRunner runner, CheckpointInfo fromCheckpoint, CancellationToken cancellationToken = default)
    {
        Run run = await runner.ResumeAsync(fromCheckpoint, cancellationToken).ConfigureAwait(false);
        return new(run, runner);
    }

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
    public static ValueTask<StreamingRun> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: null, runId);
        return StreamAsync(runner, (object)input, cancellationToken);
    }

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
    public static ValueTask<StreamingRun> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: null, runId);
        return StreamAsync(runner, input, cancellationToken);
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
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return StreamCheckpointedAsync(runner, (object)input, cancellationToken);
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
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{StreamingRun}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="StreamingRun"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Checkpointed<StreamingRun>> StreamAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return StreamCheckpointedAsync(runner, input, cancellationToken);
    }

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
    public static ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return ResumeStreamCheckpointedAsync(runner, fromCheckpoint, cancellationToken);
    }

    /// <summary>
    /// Resumes an asynchronous streaming execution for the specified input from a checkpoint.
    /// </summary>
    /// <remarks>If the operation is cancelled via the <paramref name="cancellationToken"/> token, the streaming execution will
    /// be terminated.</remarks>
    /// <typeparam name="TInput">The type of input accepted by the workflow. Must be non-nullable.</typeparam>
    /// <param name="workflow">The workflow to be executed. Must not be <c>null</c>.</param>
    /// <param name="fromCheckpoint">The <see cref="CheckpointInfo"/> corresponding to the checkpoint from which to resume.</param>
    /// <param name="checkpointManager">The <see cref="CheckpointManager"/> to use with this run.</param>
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="StreamingRun"/> that provides access to the results of the streaming run.</returns>
    public static ValueTask<Checkpointed<StreamingRun>> ResumeStreamAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return ResumeStreamCheckpointedAsync(runner, fromCheckpoint, cancellationToken);
    }

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
    public static ValueTask<Run> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: null, runId);
        return RunAsync(runner, (object)input, cancellationToken);
    }

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
    public static ValueTask<Run> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: null, runId);
        return RunAsync(runner, input, cancellationToken);
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
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: checkpointManager, runId);
        return RunCheckpointedAsync(runner, (object)input, cancellationToken);
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
    /// <param name="runId">An optional unique identifier for the run. If not provided, a new identifier will be generated.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{Run}"/> that represents the asynchronous operation. The result contains a <see
    /// cref="Run"/> for managing and interacting with the streaming run.</returns>
    public static ValueTask<Checkpointed<Run>> RunAsync<TInput>(
        Workflow<TInput> workflow,
        TInput input,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager: checkpointManager, runId);
        return RunCheckpointedAsync(runner, input, cancellationToken);
    }

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
    public static ValueTask<Checkpointed<Run>> ResumeAsync(
        Workflow workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default)
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return ResumeRunCheckpointedAsync(runner, fromCheckpoint, cancellationToken);
    }

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
    public static ValueTask<Checkpointed<Run>> ResumeAsync<TInput>(
        Workflow<TInput> workflow,
        CheckpointInfo fromCheckpoint,
        CheckpointManager checkpointManager,
        string? runId = null,
        CancellationToken cancellationToken = default) where TInput : notnull
    {
        InProcessRunner runner = CreateRunner(workflow, checkpointManager, runId);
        return ResumeRunCheckpointedAsync(runner, fromCheckpoint, cancellationToken);
    }
}
