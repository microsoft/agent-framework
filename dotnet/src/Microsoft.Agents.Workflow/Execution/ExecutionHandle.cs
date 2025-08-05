// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal interface ISuperStepRunner
{
    ValueTask EnqueueMessageAsync(object message);

    event EventHandler<WorkflowEvent>? WorkflowEvent;

    ValueTask<bool> RunSuperStepAsync(CancellationToken cancellation);
}

internal interface IRunnerWithResult<TResult>
{
    ISuperStepRunner StepRunner { get; }

    ValueTask<TResult> GetResultAsync(CancellationToken cancellation = default);
}

/// <summary>
/// .
/// </summary>
public class StreamingExecutionHandle
{
    private readonly ISuperStepRunner _stepRunner;

    internal StreamingExecutionHandle(ISuperStepRunner stepRunner)
    {
        this._stepRunner = Throw.IfNull(stepRunner);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="response"></param>
    /// <returns></returns>
    /// <exception cref="NotImplementedException"></exception>
    public ValueTask SendResponseAsync(object response)
    {
        return this._stepRunner.EnqueueMessageAsync(response);
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="cancellation"></param>
    /// <returns></returns>
    /// <exception cref="NotImplementedException"></exception>
    public async IAsyncEnumerable<WorkflowEvent> WatchStreamAsync([EnumeratorCancellation] CancellationToken cancellation)
    {
        List<WorkflowEvent> eventSink = new();

        this._stepRunner.WorkflowEvent += OnWorkflowEvent;

        try
        {
            while (await this._stepRunner.RunSuperStepAsync(cancellation).ConfigureAwait(false))
            {
                List<WorkflowEvent> outputEvents = Interlocked.Exchange(ref eventSink, new());
                foreach (WorkflowEvent raisedEvent in outputEvents)
                {
                    yield return raisedEvent;
                }
            }
        }
        finally
        {
            this._stepRunner.WorkflowEvent -= OnWorkflowEvent;
        }

        void OnWorkflowEvent(object? sender, WorkflowEvent e)
        {
            eventSink.Add(e);
        }
    }
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="TResult"></typeparam>
public class StreamingExecutionHandle<TResult> : StreamingExecutionHandle
{
    private readonly IRunnerWithResult<TResult> _resultSource;

    internal StreamingExecutionHandle(IRunnerWithResult<TResult> runner)
        : base(Throw.IfNull(runner.StepRunner))
    {
        this._resultSource = runner;
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="cancellation"></param>
    /// <returns></returns>
    /// <exception cref="NotImplementedException"></exception>
    public ValueTask<TResult> GetResultAsync(CancellationToken cancellation = default)
    {
        return this._resultSource.GetResultAsync(cancellation);
    }
}

/// <summary>
/// .
/// </summary>
public static class ExecutionHandleExtensions
{
    /// <summary>
    /// Processes all events from the workflow execution stream until completion.
    /// </summary>
    /// <remarks>This method continuously monitors the workflow execution stream provided by <paramref
    /// name="handle"/> and invokes the  <paramref name="eventCallback"/> for each event. If the callback returns a
    /// non-<see langword="null"/> response, the response  is sent back to the workflow using the handle.</remarks>
    /// <param name="handle">The <see cref="StreamingExecutionHandle"/> representing the workflow execution stream to monitor.</param>
    /// <param name="eventCallback">An optional callback function invoked for each <see cref="WorkflowEvent"/> received from the stream.  The
    /// callback can return a response object to be sent back to the workflow, or <see langword="null"/> if no response
    /// is required.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> to observe while waiting for events. Defaults to <see
    /// cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous operation. The task completes when the workflow
    /// execution stream is fully processed.</returns>
    public static async ValueTask RunToCompletionAsync(this StreamingExecutionHandle handle, Func<WorkflowEvent, object?>? eventCallback = null, CancellationToken cancellation = default)
    {
        Throw.IfNull(handle);

        await foreach (WorkflowEvent @event in handle.WatchStreamAsync(cancellation).ConfigureAwait(false))
        {
            object? maybeResponse = eventCallback?.Invoke(@event);
            if (maybeResponse != null)
            {
                await handle.SendResponseAsync(maybeResponse).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Executes the workflow associated with the specified <see cref="StreamingExecutionHandle{TResult}"/>  until it
    /// completes and returns the final result.
    /// </summary>
    /// <remarks>This method ensures that the workflow runs to completion before returning the result.  If an
    /// <paramref name="eventCallback"/> is provided, it will be invoked for each event emitted  during the workflow's
    /// execution, allowing for custom event handling.</remarks>
    /// <typeparam name="TResult">The type of the result produced by the workflow.</typeparam>
    /// <param name="handle">The <see cref="StreamingExecutionHandle{TResult}"/> representing the workflow to execute.  This parameter cannot
    /// be <see langword="null"/>.</param>
    /// <param name="eventCallback">An optional callback function that is invoked for each <see cref="WorkflowEvent"/> emitted during  the workflow
    /// execution. The callback can process the event and return an object, or <see langword="null"/>  if no processing
    /// is required.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the workflow execution.  The default value is <see
    /// cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask{TResult}"/> that represents the asynchronous operation. The task's result  is the final
    /// result of the workflow execution.</returns>
    public static async ValueTask<TResult> RunToCompletionAsync<TResult>(this StreamingExecutionHandle<TResult> handle, Func<WorkflowEvent, object?>? eventCallback = null, CancellationToken cancellation = default)
    {
        Throw.IfNull(handle);

        await handle.RunToCompletionAsync(eventCallback, cancellation).ConfigureAwait(false);
        return await handle.GetResultAsync(cancellation).ConfigureAwait(false);
    }
}
