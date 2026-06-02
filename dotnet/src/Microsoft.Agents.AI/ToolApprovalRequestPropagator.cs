// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Propagates approval requests produced while executing a function back to the
/// <see cref="FunctionCallContent"/> that caused that execution.
/// </summary>
internal static class ToolApprovalRequestPropagator
{
    private static readonly ConcurrentDictionary<string, IReadOnlyList<ToolApprovalRequestContent>> s_approvals = new();

    /// <summary>
    /// Attaches approval requests to the specified function call.
    /// </summary>
    /// <param name="functionCall">The function call that caused the approval requests.</param>
    /// <param name="approvalRequests">The approval requests to attach.</param>
    public static void Attach(FunctionCallContent functionCall, IEnumerable<ToolApprovalRequestContent> approvalRequests)
    {
        if (approvalRequests is null)
        {
            s_approvals.TryRemove(functionCall.CallId, out _);
            return;
        }

        var approvals = approvalRequests as IReadOnlyList<ToolApprovalRequestContent> ?? approvalRequests.ToList();
        if (approvals.Count == 0)
        {
            s_approvals.TryRemove(functionCall.CallId, out _);
            return;
        }

        s_approvals[functionCall.CallId] = approvals;
    }

    /// <summary>
    /// Gets approval requests previously attached to the specified function call.
    /// </summary>
    /// <param name="functionCall">The function call whose approval requests should be retrieved.</param>
    /// <returns>The attached approval requests, or <see langword="null"/> if none are available.</returns>
    public static IReadOnlyList<ToolApprovalRequestContent>? GetApprovals(FunctionCallContent functionCall)
        => s_approvals.TryGetValue(functionCall.CallId, out var approvals) ? approvals : null;

    /// <summary>
    /// Removes and returns approval requests previously attached to the specified function call.
    /// </summary>
    /// <param name="functionCall">The function call whose approval requests should be removed.</param>
    /// <returns>The removed approval requests, or <see langword="null"/> if none are available.</returns>
    public static IReadOnlyList<ToolApprovalRequestContent>? TakeApprovals(FunctionCallContent functionCall)
        => s_approvals.TryRemove(functionCall.CallId, out var approvals) ? approvals : null;
}
