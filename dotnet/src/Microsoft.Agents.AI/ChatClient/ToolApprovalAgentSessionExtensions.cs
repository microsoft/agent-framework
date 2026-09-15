// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for reading and closing human-in-the-loop tool approval state on an
/// <see cref="AgentSession"/>.
/// </summary>
/// <remarks>
/// <para>
/// When a run surfaces <see cref="ToolApprovalRequestContent"/> and is cancelled, refreshed, or otherwise
/// interrupted before the host submits a matching <see cref="ToolApprovalResponseContent"/>, the framework
/// retains those requests in session state. Durable hosts can enumerate them after restore, re-surface UI,
/// or drain them as explicit rejections before accepting a new normal user turn (#7862, #7872).
/// </para>
/// <para>
/// Rejection helpers return response content the host should send on the next agent run so
/// <see cref="FunctionInvokingChatClient"/> can emit terminal <see cref="FunctionResultContent"/> and close
/// the tool lifecycle. Pending bag entries stay until those responses are validated and consumed on that run;
/// clearing the bag first would drop the only binding authority on restore paths where message history has a
/// dangling <see cref="FunctionCallContent"/> without a matching approval request.
/// </para>
/// </remarks>
public static class ToolApprovalAgentSessionExtensions
{
    /// <summary>
    /// Attempts to retrieve the tool approval requests that the framework has surfaced for the specified session
    /// and that have not yet been answered with a matching <see cref="ToolApprovalResponseContent"/>.
    /// </summary>
    /// <param name="session">The agent session to read pending approval requests from.</param>
    /// <param name="requests">
    /// When this method returns, contains deep snapshots of the pending approval requests if any were found;
    /// otherwise, <see langword="null"/>.
    /// </param>
    /// <returns>
    /// <see langword="true"/> if at least one pending approval request was found; otherwise,
    /// <see langword="false"/>.
    /// </returns>
    public static bool TryGetPendingToolApprovalRequests(
        this AgentSession session,
        [NotNullWhen(true)] out IReadOnlyList<ToolApprovalRequestContent>? requests)
    {
        _ = Throw.IfNull(session);

        if (session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
                ApprovalResponseBindingChatClient.StateBagKey,
                out var pending,
                AgentJsonUtilities.DefaultOptions)
            && pending is { Count: > 0 })
        {
            // Deep-snapshot each request so hosts cannot mutate FunctionCallContent.Arguments on the
            // model-originated binding authority retained in the session bag.
            var snapshots = new List<ToolApprovalRequestContent>(pending.Count);
            foreach (var request in pending)
            {
                snapshots.Add(ApprovalResponseBindingChatClient.SnapshotRequest(request));
            }

            requests = snapshots;
            return true;
        }

        requests = null;
        return false;
    }

    /// <summary>
    /// Creates rejection responses for every pending tool approval request on the session.
    /// </summary>
    /// <param name="session">The agent session whose pending approvals should be closed.</param>
    /// <param name="reason">
    /// An optional reason recorded on each rejection (for example cancellation or host-initiated drain).
    /// </param>
    /// <returns>
    /// The rejection responses to send on the next agent run so the function loop can emit terminal
    /// <see cref="FunctionResultContent"/>. Empty when nothing was pending. Pending bag entries remain until
    /// those responses are bound and consumed on that run.
    /// </returns>
    public static IReadOnlyList<ToolApprovalResponseContent> CreatePendingApprovalRejections(
        this AgentSession session,
        string? reason = null)
    {
        _ = Throw.IfNull(session);

        if (!session.TryGetPendingToolApprovalRequests(out var pending))
        {
            return [];
        }

        var responses = new List<ToolApprovalResponseContent>(pending.Count);
        foreach (var request in pending)
        {
            responses.Add(request.CreateResponse(approved: false, reason));
        }

        // Do not clear the bag here. On restore, history may only contain a dangling FunctionCallContent;
        // ValidateInboundApprovalResponses needs these entries to honor the returned rejections.
        return responses;
    }

    /// <summary>
    /// Removes all pending tool approval requests from the session without creating rejection responses.
    /// </summary>
    /// <param name="session">The agent session to clear.</param>
    /// <returns>
    /// <see langword="true"/> if pending approval state was present and removed; otherwise,
    /// <see langword="false"/>.
    /// </returns>
    /// <remarks>
    /// Prefer <see cref="CreatePendingApprovalRejections"/> when the host can still run the agent, so the
    /// function loop can close each tool call with a terminal result. Use this only when discarding binding
    /// authority intentionally without producing responses.
    /// </remarks>
    public static bool ClearPendingToolApprovalRequests(this AgentSession session)
    {
        _ = Throw.IfNull(session);
        return session.StateBag.TryRemoveValue(ApprovalResponseBindingChatClient.StateBagKey);
    }
}
