// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A <see cref="Workflow"/> run instance supporting a streaming form of receiving workflow events, and providing
/// a mechanism to send responses back to the workflow.
/// </summary>
public sealed class StreamingRun
{
    private TaskCompletionSource<object>? _waitForResponseSource;
    private readonly ISuperStepRunner _stepRunner;

    private static readonly string s_namespace = typeof(StreamingRun).Namespace!;
    private static readonly ActivitySource s_activitySource = new(s_namespace);

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
    /// A unique identifier for the run. Can be provided at the start of the run, or auto-generated.
    /// </summary>
    public string RunId => this._stepRunner.RunId;

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

    internal async ValueTask<bool> TrySendMessageUntypedAsync(object message, Type messageType)
    {
        Throw.IfNull(message);

        if (message is ExternalResponse response)
        {
            await this.SendResponseAsync(response).ConfigureAwait(false);
            return true;
        }

        return await this._stepRunner.EnqueueMessageUntypedAsync(message, messageType).ConfigureAwait(false);
    }

    /// <summary>
    /// Asynchronously streams workflow events as they occur during workflow execution.
    /// </summary>
    /// <remarks>This method yields <see cref="WorkflowEvent"/> instances in real time as the workflow
    /// progresses. The stream completes when a <see cref="RequestHaltEvent"/> is encountered. Events are
    /// delivered in the order they are raised.</remarks>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> that can be used to cancel the streaming operation. If cancellation is
    /// requested, the stream will end and no further events will be yielded.</param>
    /// <returns>An asynchronous stream of <see cref="WorkflowEvent"/> objects representing significant workflow state changes.
    /// The stream ends when the workflow completes or when cancellation is requested.</returns>
    public IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        CancellationToken cancellationToken = default)
        => this.WatchStreamAsync(blockOnPendingRequest: true, cancellationToken);

    internal async IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        bool blockOnPendingRequest,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        List<WorkflowEvent> eventSink = [];

        this._stepRunner.WorkflowEvent += OnWorkflowEvent;

        using Activity? activity = s_activitySource.StartActivity(ActivityNames.WorkflowRun);
        activity?.SetTag(Tags.WorkflowId, this._stepRunner.StartExecutorId).SetTag(Tags.RunId, this.RunId);

        try
        {
            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowStarted));
            do
            {
                // Because we may be yielding out of this function, we need to ensure that the Activity.Current
                // is set to our activity for the duration of this loop iteration.
                Activity.Current = activity;

                // Drain SuperSteps while there are steps to run
                try
                {
                    await this._stepRunner.RunSuperStepAsync(cancellationToken).ConfigureAwait(false);
                }
                catch (Exception ex) when (activity is not null)
                {
                    activity.AddEvent(new ActivityEvent(EventNames.WorkflowError, tags: new() {
                        { Tags.ErrorType, ex.GetType().FullName },
                        { Tags.BuildErrorMessage, ex.Message },
                    }));
                    activity.CaptureException(ex);
                    throw;
                }

                if (cancellationToken.IsCancellationRequested)
                {
                    yield break; // Exit if cancellation is requested
                }

                bool hadCompletionEvent = false;
                foreach (WorkflowEvent raisedEvent in Interlocked.Exchange(ref eventSink, []))
                {
                    if (cancellationToken.IsCancellationRequested)
                    {
                        yield break; // Exit if cancellation is requested
                    }

                    // TODO: Do we actually want to interpret this as a termination request?
                    if (raisedEvent is RequestHaltEvent)
                    {
                        hadCompletionEvent = true;
                    }
                    else
                    {
                        yield return raisedEvent;
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

                    using CancellationTokenRegistration registration = cancellationToken.Register(() => this._waitForResponseSource?.SetResult(new()));

                    await this._waitForResponseSource.Task.ConfigureAwait(false);
                    this._waitForResponseSource = null;
                }
            } while (this._stepRunner.HasUnprocessedMessages);

            activity?.AddEvent(new ActivityEvent(EventNames.WorkflowCompleted));
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

    /// <summary>
    /// Signals the end of the current run and initiates any necessary cleanup operations asynchronously.
    /// Enables the underlying Workflow instance to be reused in subsequent runs.
    /// </summary>
    /// <returns>A ValueTask that represents the asynchronous operation. The task is complete when the run has
    /// ended and cleanup is finished.</returns>
    public ValueTask EndRunAsync() => this._stepRunner.RequestEndRunAsync();
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
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous operation. The task completes when the workflow
    /// execution stream is fully processed.</returns>
    public static async ValueTask RunToCompletionAsync(this StreamingRun handle, Func<WorkflowEvent, ExternalResponse?>? eventCallback = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(handle);

        await foreach (WorkflowEvent @event in handle.WatchStreamAsync(cancellationToken).ConfigureAwait(false))
        {
            ExternalResponse? maybeResponse = eventCallback?.Invoke(@event);
            if (maybeResponse is not null)
            {
                await handle.SendResponseAsync(maybeResponse).ConfigureAwait(false);
            }
        }
    }
}
