// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

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
            if (maybeResponse != null)
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
        return (await handle.GetRunningOutputAsync(cancellation).ConfigureAwait(false))!;
    }
}
