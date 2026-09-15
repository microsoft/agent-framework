// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for reading human-in-the-loop tool approval state from an <see cref="AgentSession"/>.
/// </summary>
public static class ToolApprovalAgentSessionExtensions
{
    /// <summary>
    /// Attempts to retrieve the tool approval requests that the framework has surfaced for the specified session and
    /// that have not yet been answered with a matching <see cref="ToolApprovalResponseContent"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A host with durable sessions can use this after deserializing a session to discover that the conversation is
    /// paused on a pending approval, restore its approval UI, and submit the approval later using
    /// the request id.
    /// </para>
    /// <para>
    /// The returned requests are snapshots of the model-originated requests. Mutating them does not change the
    /// recorded state used to bind an incoming approval response.
    /// </para>
    /// </remarks>
    /// <param name="session">The agent session to read pending approval requests from.</param>
    /// <param name="requests">When this method returns, contains the pending approval requests if any were found; otherwise, <see langword="null"/>.</param>
    /// <returns><see langword="true"/> if at least one pending approval request was found; <see langword="false"/> otherwise.</returns>
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
            requests = pending;
            return true;
        }

        requests = null;
        return false;
    }
}
