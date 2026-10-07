// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

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

    private readonly Dictionary<string, TaskCompletionSource<TResult>> _pending = new(StringComparer.Ordinal);
    private readonly Queue<string> _settledQueue = new();
    private readonly HashSet<string> _settledSet = new(StringComparer.Ordinal);
    private readonly int _settledQueueSize;

    // Guards _pending, _settledQueue, and _settledSet so that registration, removal, and
    // settled-tracking are a single atomic transition.
    private readonly object _lock = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="AsyncRequestBroker{TResult}"/> class.
    /// </summary>
    /// <param name="settledQueueSize">Maximum number of recently settled request IDs to track for late-response handling.</param>
    public AsyncRequestBroker(int settledQueueSize = DefaultSettledQueueSize)
    {
        if (settledQueueSize < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(settledQueueSize), "Settled queue size must be at least 1.");
        }

        this._settledQueueSize = settledQueueSize;
    }

    /// <summary>Gets the number of requests currently awaiting a response.</summary>
    public int PendingCount
    {
        get
        {
            lock (this._lock)
            {
                return this._pending.Count;
            }
        }
    }

    /// <summary>Suspend until the request is resolved, rejected, or cancelled.</summary>
    /// <param name="requestId">Unique identifier for this request.</param>
    /// <param name="timeout">
    /// Optional timeout. <see langword="null"/> or <see cref="Timeout.InfiniteTimeSpan"/> waits indefinitely.
    /// Otherwise must be non-negative and no greater than <see cref="int.MaxValue"/> milliseconds.
    /// </param>
    /// <param name="cancellationToken">Token to cancel the wait.</param>
    /// <returns>The result passed to <see cref="Resolve"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="requestId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="timeout"/> is outside the supported range.</exception>
    /// <exception cref="InvalidOperationException">The request ID is already pending or was recently settled.</exception>
    /// <exception cref="OperationCanceledException">The timeout elapsed or <paramref name="cancellationToken"/> was cancelled.</exception>
    public async Task<TResult> RequestAsync(string requestId, TimeSpan? timeout = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(requestId);

        bool hasTimeout = timeout.HasValue && timeout.Value != Timeout.InfiniteTimeSpan;
        if (hasTimeout && (timeout!.Value < TimeSpan.Zero || timeout.Value.TotalMilliseconds > int.MaxValue))
        {
            throw new ArgumentOutOfRangeException(nameof(timeout), timeout, "Timeout must be non-negative and no greater than Int32.MaxValue milliseconds, or Timeout.InfiniteTimeSpan.");
        }

        var tcs = new TaskCompletionSource<TResult>(TaskCreationOptions.RunContinuationsAsynchronously);

        lock (this._lock)
        {
            if (this._settledSet.Contains(requestId))
            {
                throw new InvalidOperationException($"Request '{requestId}' was already settled.");
            }

            if (this._pending.ContainsKey(requestId))
            {
                throw new InvalidOperationException($"Request '{requestId}' is already pending.");
            }

            this._pending.Add(requestId, tcs);
        }

        using var cts = hasTimeout
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : null;

        // The timeout was validated above, so CancelAfter cannot throw here.
        cts?.CancelAfter(timeout!.Value);

        var effectiveToken = cts?.Token ?? cancellationToken;
        using var registration = effectiveToken.Register(() =>
        {
            bool removed;
            lock (this._lock)
            {
                // Only cancel our own TCS, never a replacement registered under the same ID.
                removed = this._pending.TryGetValue(requestId, out var current) && ReferenceEquals(current, tcs);
                if (removed)
                {
                    this._pending.Remove(requestId);
                    this.TrackSettledLocked(requestId);
                }
            }

            if (removed)
            {
                tcs.TrySetCanceled(effectiveToken);
            }
        });

        return await tcs.Task.ConfigureAwait(false);
    }

    /// <summary>Deliver a successful result to a waiting <see cref="RequestAsync"/> call.</summary>
    /// <param name="requestId">The request identifier.</param>
    /// <param name="result">The result to deliver.</param>
    /// <returns>
    /// <see langword="true"/> if a waiter was notified; <see langword="false"/> if the request was not found
    /// (already settled, timed out, cancelled, or never registered).
    /// </returns>
    public bool Resolve(string requestId, TResult result)
    {
        if (!this.TryRemovePending(requestId, out var tcs))
        {
            return false;
        }

        tcs.TrySetResult(result);
        return true;
    }

    /// <summary>Deliver an exception to a waiting <see cref="RequestAsync"/> call.</summary>
    /// <param name="requestId">The request identifier.</param>
    /// <param name="exception">The exception to deliver.</param>
    /// <returns>
    /// <see langword="true"/> if a waiter was notified; <see langword="false"/> if the request was not found
    /// (already settled, timed out, cancelled, or never registered).
    /// </returns>
    public bool Reject(string requestId, Exception exception)
    {
        _ = Throw.IfNull(exception);

        if (!this.TryRemovePending(requestId, out var tcs))
        {
            return false;
        }

        tcs.TrySetException(exception);
        return true;
    }

    private bool TryRemovePending(string requestId, [NotNullWhen(true)] out TaskCompletionSource<TResult>? tcs)
    {
        _ = Throw.IfNull(requestId);

        lock (this._lock)
        {
            if (!this._pending.TryGetValue(requestId, out tcs))
            {
                return false;
            }

            this._pending.Remove(requestId);
            this.TrackSettledLocked(requestId);
            return true;
        }
    }

    // Caller must hold _lock.
    private void TrackSettledLocked(string requestId)
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
