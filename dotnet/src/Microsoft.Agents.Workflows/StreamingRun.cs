// Copyright (c) Microsoft. All rights reserved.

//using System;
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
    private TaskCompletionSource<object>? _waitForResponseSource = null;
    private readonly IAsyncRunHandle _runHandle;

    internal StreamingRun(IAsyncRunHandle _runHandle)
    {
        this._runHandle = Throw.IfNull(_runHandle);
    }

    /// <summary>
    /// Asynchronously sends the specified response to the external system and signals completion of the current
    /// response wait operation.
    /// </summary>
    /// <remarks>The response will be queued for processing for the next superstep.</remarks>
    /// <param name="response">The <see cref="ExternalResponse"/> to send. Must not be <c>null</c>.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous send operation.</returns>
    public async ValueTask SendResponseAsync(ExternalResponse response)
    {
        this._waitForResponseSource?.TrySetResult(new());

        await this._runHandle.EnqueueResponseAsync(response).ConfigureAwait(false);
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
    public async ValueTask<bool> TrySendMessageAsync<TMessage>(TMessage message) where TMessage : notnull
    {
        Throw.IfNull(message);

        if (message is ExternalResponse response)
        {
            await this.SendResponseAsync(response).ConfigureAwait(false);
            return true;
        }

        return await this._runHandle.EnqueueMessageAsync(message).ConfigureAwait(false);
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
        RunStatus runStatus;
        do
        {
            // Run until we hit a halt condition
            await foreach (WorkflowEvent @event in this._runHandle.ForwardEventsAsync(breakOnHalt: true, cancellation)
                                                                  .WithCancellation(cancellation)
                                                                  .ConfigureAwait(false))
            {
                yield return @event;
            }

            runStatus = await this._runHandle.GetStatusAsync(cancellation).ConfigureAwait(false);
            if (runStatus == RunStatus.Completed)
            {
                // If we have completed the run, we can exit out of the loop
                yield break;
            }

            // If we do not have any actions to take on the Workflow, but have unprocessed
            // requests, wait for the responses to come in before exiting out of the workflow
            // execution.
            if (blockOnPendingRequest &&
                runStatus == RunStatus.PendingRequests)
            {
                if (this._waitForResponseSource == null)
                {
                    this._waitForResponseSource = new();
                }

                using CancellationTokenRegistration registration = cancellation.Register(() =>
                {
                    this._waitForResponseSource?.SetResult(new());
                });

                await this._waitForResponseSource.Task.ConfigureAwait(false);
                this._waitForResponseSource = null;
            }
        } while (runStatus == RunStatus.Idle || runStatus == RunStatus.Running);
    }
}

/// <summary>
/// A <see cref="Workflow"/> run instance supporting a streaming form of receiving workflow events, providing
/// a mechanism to send responses back to the workflow, and retrieving the result of workflow execution.
/// </summary>
/// <typeparam name="TResult">The type of the workflow output.</typeparam>
public class StreamingRun<TResult> : StreamingRun
{
    private readonly IRunHandleWithOutput<TResult> _resultSource;

    internal StreamingRun(IRunHandleWithOutput<TResult> handleWithOutput)
        : base(Throw.IfNull(handleWithOutput.RunHandle))
    {
        this._resultSource = handleWithOutput;
    }

    /// <summary>
    /// Retrieves the current output value if available, even if the operation has not yet completed.
    /// </summary>
    /// <param name="cancellation">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A ValueTask containing the current output value if available; otherwise, null if no output has been produced
    /// yet.</returns>
    public ValueTask<TResult?> GetRunningOutputAsync(CancellationToken cancellation = default)
        => this._resultSource.GetRunningOutputAsync(cancellation);
}
