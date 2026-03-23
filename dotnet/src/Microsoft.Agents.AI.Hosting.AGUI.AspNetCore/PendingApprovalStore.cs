// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Stores pending permission approval requests keyed by request ID.
/// Each pending request is backed by a <see cref="TaskCompletionSource{TResult}"/>
/// that blocks the Copilot SDK's OnPermissionRequest callback until
/// the AG-UI client responds via the /approve endpoint.
/// </summary>
internal sealed class PendingApprovalStore
{
    private readonly ConcurrentDictionary<string, PendingApproval> _pendingApprovals = new(StringComparer.Ordinal);

    /// <summary>
    /// Registers a new pending approval and returns a task that completes
    /// when the client responds or the timeout expires.
    /// </summary>
    /// <param name="requestId">Unique identifier for this approval request.</param>
    /// <param name="timeout">How long to wait for client response before auto-denying.</param>
    /// <returns>A task that resolves to <c>true</c> if approved, <c>false</c> if denied or timed out.</returns>
    public Task<bool> RegisterAsync(string requestId, TimeSpan timeout)
    {
        Trace.TraceInformation("[AGUI-HITL] Registering pending approval: RequestId={0}, TimeoutSeconds={1}", requestId, timeout.TotalSeconds);

        var cts = new CancellationTokenSource(timeout);
        var tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

        var pending = new PendingApproval(tcs, cts);

        if (!this._pendingApprovals.TryAdd(requestId, pending))
        {
            cts.Dispose();
            Trace.TraceWarning("[AGUI-HITL] Duplicate approval request ID: {0}", requestId);
            throw new InvalidOperationException($"A pending approval with request ID '{requestId}' already exists.");
        }

        // Auto-deny on timeout
        cts.Token.Register(() =>
        {
            if (this._pendingApprovals.TryRemove(requestId, out var removed))
            {
                Trace.TraceWarning("[AGUI-HITL] Approval TIMED OUT, auto-denying: RequestId={0}, TimeoutSeconds={1}", requestId, timeout.TotalSeconds);
                removed.TaskCompletionSource.TrySetResult(false);
                removed.CancellationTokenSource.Dispose();
            }
        });

        Trace.TraceInformation("[AGUI-HITL] Approval registered, waiting for client response: RequestId={0}", requestId);
        return tcs.Task;
    }

    /// <summary>
    /// Completes a pending approval with the client's decision.
    /// </summary>
    /// <param name="requestId">The request ID to complete.</param>
    /// <param name="approved">Whether the client approved the request.</param>
    /// <returns><c>true</c> if the request was found and completed; <c>false</c> if not found or already completed.</returns>
    public bool TryComplete(string requestId, bool approved)
    {
        if (this._pendingApprovals.TryRemove(requestId, out var pending))
        {
            bool completed = pending.TaskCompletionSource.TrySetResult(approved);
            pending.CancellationTokenSource.Dispose();
            Trace.TraceInformation("[AGUI-HITL] Approval completed: RequestId={0}, Approved={1}", requestId, approved);
            return completed;
        }

        Trace.TraceWarning("[AGUI-HITL] TryComplete not found: RequestId={0}", requestId);
        return false;
    }

    private sealed record PendingApproval(
        TaskCompletionSource<bool> TaskCompletionSource,
        CancellationTokenSource CancellationTokenSource);
}
