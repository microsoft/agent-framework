// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Resolves the key used to restore an agent session for a Responses request.
/// </summary>
internal static class HostedAgentSessionKey
{
    /// <summary>
    /// Uses the conversation head, a previous response snapshot, or the new response ID for a first turn.
    /// Conversation and previous response IDs are mutually exclusive in a valid request.
    /// </summary>
    /// <remarks>
    /// IDs are opaque. Unlike Foundry response IDs, these IDs do not encode a shared partition;
    /// distinct previous response IDs must keep identifying independent snapshots.
    /// </remarks>
    public static string Resolve(string? conversationId, string? previousResponseId, string responseId)
    {
        if (!string.IsNullOrWhiteSpace(conversationId))
        {
            return conversationId;
        }

        if (!string.IsNullOrWhiteSpace(previousResponseId))
        {
            return previousResponseId;
        }

        ArgumentException.ThrowIfNullOrWhiteSpace(responseId);
        return responseId;
    }
}
