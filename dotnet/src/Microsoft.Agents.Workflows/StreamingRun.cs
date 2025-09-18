// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A <see cref="Workflow"/> run instance supporting a streaming form of receiving workflow events, and providing
/// a mechanism to send responses back to the workflow.
/// </summary>
public class StreamingRun
{
    private TaskCompletionSource<object>? _waitForResponseSource;
    private readonly ISuperStepRunner _stepRunner;

    /// <summary>
    /// Gets a value indicating whether there are any outstanding <see cref="ExternalRequest"/>s for which a
    /// <see cref="ExternalResponse"/> has not been sent.
    /// </summary>
    public bool HasUnservicedRequests => this._stepRunner.HasUnservicedRequests;

    internal StreamingRun(ISuperStepRunner stepRunner)
    {
        this._stepRunner = Throw.IfNull(stepRunner);
    }

    /// <summary>
    /// Asynchronously sends the specified response to the external system and signals completion of the current
    /// response wait operation.
    /// </summary>
    /// <remarks>The response will be queued for processing for the next superstep.</remarks>
    /// <param name="response">The <see cref="ExternalResponse"/> to send. Must not be <c>null</c>.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous send operation.</returns>
    public ValueTask SendResponseAsync(ExternalResponse response)
    {
        this._waitForResponseSource?.TrySetResult(new());

        return this._stepRunner.EnqueueResponseAsync(response);
    }

    /// <summary>
    /// Attempts to send the specified message asynchronously and returns a value indicating whether the operation was
    /// successful.
    /// </summary>
    /// <typeparam name="TMessage">The type of the message to send. Must be compatible with the expected message types for
    /// the starting executor, or receiving port.</typeparam>
    /// <param name="message">The message instance to send. Cannot be null.</param>
    /// <returns>A <see cref="ValueTask{Boolean}"/> that represents the asynchronous send operation. It's
    /// <see cref="ValueTask{Boolean}.Result"/> is <see langword="true"/> if the message was sent
    /// successfully; otherwise, <see langword="false"/>.</returns>
    public async ValueTask<bool> TrySendMessageAsync<TMessage>(TMessage message)
    {
        Throw.IfNull(message);

        if (message is ExternalResponse response)
        {
            await this.SendResponseAsync(response).ConfigureAwait(false);
            return true;
        }

        return await this._stepRunner.EnqueueMessageAsync(message).ConfigureAwait(false);
    }

    /// <summary>
    /// Asynchronously streams workflow events as they occur during workflow execution.
    /// </summary>
    /// <remarks>This method yields <see cref="WorkflowEvent"/> instances in real time as the workflow
    /// progresses. The stream completes when a <see cref="WorkflowCompletedEvent"/> is encountered. Events are
    /// delivered in the order they are raised.</remarks>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation. If cancellation is
    /// requested, the stream will end and no further events will be yielded.</param>
    /// <returns>An asynchronous stream of <see cref="WorkflowEvent"/> objects representing significant workflow state changes.
    /// The stream ends when the workflow completes or when cancellation is requested.</returns>
    public IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        CancellationToken cancellation = default)
        => this.WatchStreamAsync(blockOnPendingRequest: true, cancellation);

    internal async IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        bool blockOnPendingRequest,
        [EnumeratorCancellation] CancellationToken cancellation = default)
    {
        List<WorkflowEvent> eventSink = [];

        this._stepRunner.WorkflowEvent += OnWorkflowEvent;

        try
        {
            do
            {
                // Drain SuperSteps while there are steps to run
                await this._stepRunner.RunSuperStepAsync(cancellation).ConfigureAwait(false);
                if (cancellation.IsCancellationRequested)
                {
                    yield break; // Exit if cancellation is requested
                }

                bool hadCompletionEvent = false;
                foreach (WorkflowEvent raisedEvent in Interlocked.Exchange(ref eventSink, []))
                {
                    yield return raisedEvent;

                    if (cancellation.IsCancellationRequested)
                    {
                        yield break; // Exit if cancellation is requested
                    }

                    // TODO: Do we actually want to interpret this as a termination request?
                    if (raisedEvent is WorkflowCompletedEvent)
                    {
                        hadCompletionEvent = true;
                    }
                }

                if (hadCompletionEvent)
                {
                    // If we had a completion event, we are done.
                    yield break;
                }

                // If we do not have any actions to take on the Workflow, but have unprocessed
                // requests, wait for the responses to come in before exiting out of the workflow
                // execution.
                if (blockOnPendingRequest &&
                    !this._stepRunner.HasUnprocessedMessages &&
                    this._stepRunner.HasUnservicedRequests)
                {
                    this._waitForResponseSource ??= new();

                    using CancellationTokenRegistration registration = cancellation.Register(() => this._waitForResponseSource?.SetResult(new()));

                    await this._waitForResponseSource.Task.ConfigureAwait(false);
                    this._waitForResponseSource = null;
                }
            } while (this._stepRunner.HasUnprocessedMessages);
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
/// A <see cref="Workflow"/> run instance supporting a streaming form of receiving workflow events, providing
/// a mechanism to send responses back to the workflow, and retrieving the result of workflow execution.
/// </summary>
/// <typeparam name="TResult">The type of the workflow output.</typeparam>
public class StreamingRun<TResult> : StreamingRun
{
    private readonly IRunnerWithOutput<TResult> _resultSource;

    internal StreamingRun(IRunnerWithOutput<TResult> runner)
        : base(Throw.IfNull(runner.StepRunner))
    {
        this._resultSource = runner;
    }

    /// <inheritdoc cref="IRunnerWithOutput{TResult}.RunningOutput"/>
    public TResult? RunningOutput => this._resultSource.RunningOutput;
}

/// <summary>
/// Provides extension methods for processing and executing workflows using streaming runs.
/// </summary>
public static class StreamingRunExtensions
{
    /// <summary>
    /// Processes all events from the workflow execution stream until completion.
    /// </summary>
    /// <remarks>This method continuously monitors the workflow execution stream provided by <paramref
    /// name="handle"/> and invokes the  <paramref name="eventCallback"/> for each event. If the callback returns a
    /// non-<see langword="null"/> response, the response  is sent back to the workflow using the handle.</remarks>
    /// <param name="handle">The <see cref="StreamingRun"/> representing the workflow execution stream to monitor.</param>
    /// <param name="eventCallback">An optional callback function invoked for each <see cref="WorkflowEvent"/> received from the stream.
    /// The callback can return a response object to be sent back to the workflow, or <see langword="null"/> if no response
    /// is required.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> to observe while waiting for events. </param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous operation. The task completes when the workflow
    /// execution stream is fully processed.</returns>
    public static async ValueTask RunToCompletionAsync(this StreamingRun handle, Func<WorkflowEvent, ExternalResponse?>? eventCallback = null, CancellationToken cancellation = default)
    {
        Throw.IfNull(handle);

        await foreach (WorkflowEvent @event in handle.WatchStreamAsync(cancellation).ConfigureAwait(false))
        {
            ExternalResponse? maybeResponse = eventCallback?.Invoke(@event);
            if (maybeResponse is not null)
            {
                await handle.SendResponseAsync(maybeResponse).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Executes the workflow associated with the specified <see cref="StreamingRun{TResult}"/>  until it
    /// completes and returns the final result.
    /// </summary>
    /// <remarks>This method ensures that the workflow runs to completion before returning the result.  If an
    /// <paramref name="eventCallback"/> is provided, it will be invoked for each event emitted  during the workflow's
    /// execution, allowing for custom event handling.</remarks>
    /// <typeparam name="TResult">The type of the result produced by the workflow.</typeparam>
    /// <param name="handle">The <see cref="StreamingRun{TResult}"/> representing the workflow to execute.</param>
    /// <param name="eventCallback">An optional callback function that is invoked for each <see cref="WorkflowEvent"/>
    /// emitted during execution. The callback can process the event and return an object, or <see langword="null"/>
    /// if no response is required.</param>
    /// <param name="cancellation">A <see cref="CancellationToken"/> that can be used to cancel the workflow execution.</param>
    /// <returns>A <see cref="ValueTask{TResult}"/> that represents the asynchronous operation. The task's result is the final
    /// result of the workflow execution.</returns>
    public static async ValueTask<TResult> RunToCompletionAsync<TResult>(this StreamingRun<TResult> handle, Func<WorkflowEvent, object?>? eventCallback = null, CancellationToken cancellation = default)
    {
        Throw.IfNull(handle);

        await handle.RunToCompletionAsync(eventCallback, cancellation).ConfigureAwait(false);
        return handle.RunningOutput!;
    }
}
