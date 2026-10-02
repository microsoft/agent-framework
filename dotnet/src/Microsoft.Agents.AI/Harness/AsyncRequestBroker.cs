// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// A generic async pause-and-wait broker for request/response patterns.
/// </summary>
/// <remarks>
/// Allows server-side code to suspend on a request ID and await a client response
/// delivered via <see cref="Resolve"/> or <see cref="Reject"/>, without polling or
/// blocking a thread.
/// </remarks>
/// <typeparam name="TResult">The type of the result delivered to the waiter.</typeparam>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AsyncRequestBroker<TResult>
{
    private const int DefaultSettledQueueSize = 256;

    private readonly ConcurrentDictionary<string, TaskCompletionSource<TResult>> _pending = new();
    private readonly Queue<string> _settledQueue = new();
    private readonly HashSet<string> _settledSet = new();
    private readonly int _settledQueueSize;
    private readonly object _settledLock = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="AsyncRequestBroker{TResult}"/> class.
    /// </summary>
    /// <param name="settledQueueSize">Maximum number of recently settled request IDs to track for late-response handling.</param>
    public AsyncRequestBroker(int settledQueueSize = DefaultSettledQueueSize)
    {
        this._settledQueueSize = settledQueueSize;
    }

    /// <summary>Gets the number of requests currently awaiting a response.</summary>
    public int PendingCount => this._pending.Count;

    /// <summary>Suspend until the request is resolved, rejected, or cancelled.</summary>
    /// <param name="requestId">Unique identifier for this request.</param>
    /// <param name="timeout">Optional timeout. <see langword="null"/> waits indefinitely.</param>
    /// <param name="cancellationToken">Token to cancel the wait.</param>
    /// <returns>The result passed to <see cref="Resolve"/>.</returns>
    public async Task<TResult> RequestAsync(string requestId, TimeSpan? timeout = null, CancellationToken cancellationToken = default)
    {
        var tcs = new TaskCompletionSource<TResult>(TaskCreationOptions.RunContinuationsAsynchronously);

        lock (this._settledLock)
        {
            if (this._settledSet.Contains(requestId))
            {
                throw new InvalidOperationException($"Request '{requestId}' was already settled.");
            }
        }

        if (!this._pending.TryAdd(requestId, tcs))
        {
            throw new InvalidOperationException($"Request '{requestId}' is already pending.");
        }

        using var cts = timeout.HasValue
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : null;

        if (cts is not null && timeout.HasValue)
        {
            cts.CancelAfter(timeout.Value);
        }

        var effectiveToken = cts?.Token ?? cancellationToken;
        using var registration = effectiveToken.Register(() =>
        {
            if (this._pending.TryRemove(requestId, out var pending))
            {
                pending.TrySetCanceled(effectiveToken);
            }
        });

        return await tcs.Task.ConfigureAwait(false);
    }

    /// <summary>Deliver a successful result to a waiting <see cref="RequestAsync"/> call.</summary>
    /// <param name="requestId">The request identifier.</param>
    /// <param name="result">The result to deliver.</param>
    /// <returns><see langword="true"/> if a waiter was notified; <see langword="false"/> if the request was not found.</returns>
    public bool Resolve(string requestId, TResult result)
    {
        if (!this._pending.TryRemove(requestId, out var tcs))
        {
            return false;
        }

        this.TrackSettled(requestId);
        tcs.TrySetResult(result);
        return true;
    }

    /// <summary>Deliver an exception to a waiting <see cref="RequestAsync"/> call.</summary>
    /// <param name="requestId">The request identifier.</param>
    /// <param name="exception">The exception to deliver.</param>
    /// <returns><see langword="true"/> if a waiter was notified.</returns>
    public bool Reject(string requestId, Exception exception)
    {
        if (!this._pending.TryRemove(requestId, out var tcs))
        {
            return false;
        }

        this.TrackSettled(requestId);
        tcs.TrySetException(exception);
        return true;
    }

    private void TrackSettled(string requestId)
    {
        lock (this._settledLock)
        {
            if (this._settledQueue.Count >= this._settledQueueSize)
            {
                string oldest = this._settledQueue.Dequeue();
                this._settledSet.Remove(oldest);
            }

            this._settledQueue.Enqueue(requestId);
            this._settledSet.Add(requestId);
        }
    }
}
