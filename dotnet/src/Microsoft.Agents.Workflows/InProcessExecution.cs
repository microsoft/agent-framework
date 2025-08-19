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
    public static ValueTask<StreamingRun> StreamAsync<TInput>(Workflow<TInput> workflow, TInput input, CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow);
        return runner.StreamAsync(input, cancellation);
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
    public static ValueTask<StreamingRun<TResult>> StreamAsync<TInput, TResult>(Workflow<TInput, TResult> workflow, TInput input, CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow);
        return runner.StreamAsync(input, cancellation);
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
    public static ValueTask<Run> RunAsync<TInput>(Workflow<TInput> workflow, TInput input, CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput> runner = new(workflow);
        return runner.RunAsync(input, cancellation);
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
    public static ValueTask<Run<TResult>> RunAsync<TInput, TResult>(Workflow<TInput, TResult> workflow, TInput input, CancellationToken cancellation = default) where TInput : notnull
    {
        InProcessRunner<TInput, TResult> runner = new(workflow);
        return runner.RunAsync(input, cancellation);
    }
}
