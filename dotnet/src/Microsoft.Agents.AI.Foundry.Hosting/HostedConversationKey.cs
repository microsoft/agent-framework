// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Derives the stable per-conversation key used to map a hosted request to a persisted MAF
/// <see cref="AgentSession"/>. The key mirrors how the AgentServer Responses SDK colocates
/// state: it prefers the request's <c>conversation_id</c>, falls back to the partition key
/// embedded in <c>previous_response_id</c>, and finally to the partition of the freshly minted
/// response id (cold start). All response ids in a chain share the same partition, so a
/// conversation continued purely via <c>previous_response_id</c> (no stored conversation) still
/// converges to a single MAF session.
/// </summary>
/// <remarks>
/// This is deliberately conversation-level: it must NOT use the container session id
/// (<c>FOUNDRY_AGENT_SESSION_ID</c> / x-agent-session-id), which is constant for the whole
/// container and serves many conversations. The id format mirrors the SDK's internal
/// <c>IdGenerator</c>: <c>{prefix}_{partition}{entropy}</c> with a 50-char body (18-char
/// partition) for the current format and a 48-char legacy body (16-char trailing partition).
/// </remarks>
internal static class HostedConversationKey
{
    private const int NewFormatBodyLength = 50;
    private const int NewFormatPartitionLength = 18;
    private const int LegacyBodyLength = 48;
    private const int LegacyPartitionLength = 16;

    /// <summary>
    /// Resolves the conversation key from conversation id, previous response id, and the minted
    /// response id, in that order. Returns <see langword="null"/> when none is available.
    /// </summary>
    public static string? Resolve(string? conversationId, string? previousResponseId, string? responseId)
    {
        if (!string.IsNullOrWhiteSpace(conversationId))
        {
            return conversationId;
        }

        return PartitionOf(previousResponseId) ?? PartitionOf(responseId);
    }

    /// <summary>
    /// Extracts the stable partition key from a response/item id. Returns <see langword="null"/>
    /// when the id is empty. Ids that don't match the known body lengths fall back to the raw value.
    /// </summary>
    public static string? PartitionOf(string? id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return null;
        }

        int delimiter = id!.IndexOf('_');
        string body = delimiter < 0 ? id : id.Substring(delimiter + 1);

        return body.Length switch
        {
            NewFormatBodyLength => body.Substring(0, NewFormatPartitionLength),
            LegacyBodyLength => body.Substring(body.Length - LegacyPartitionLength),
            _ => id,
        };
    }
}
