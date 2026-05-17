// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Rebuilds the per-turn <see cref="ChatMessage"/> list with detected attachments removed,
/// and appends renderer-produced text payloads at the end. Implements Strategy C from the
/// Phase 0 spike: a non-mutating rebuild that lets the LLM see only text.
/// </summary>
internal static class MessageBuilder
{
    public static List<ChatMessage> BuildSanitizedMessages(
        IEnumerable<ChatMessage>? source,
        HashSet<AIContent> attachmentsToStrip)
    {
        List<ChatMessage> result = new();
        if (source is null)
        {
            return result;
        }

        foreach (ChatMessage original in source)
        {
            if (original is null)
            {
                continue;
            }

            if (attachmentsToStrip.Count == 0 || original.Contents is null || original.Contents.Count == 0)
            {
                result.Add(original);
                continue;
            }

            List<AIContent>? rebuiltContents = null;
            bool anyStripped = false;
            for (int i = 0; i < original.Contents.Count; i++)
            {
                AIContent c = original.Contents[i];
                if (attachmentsToStrip.Contains(c))
                {
                    anyStripped = true;
                    rebuiltContents ??= new List<AIContent>(original.Contents.Take(i));
                    continue;
                }

                rebuiltContents?.Add(c);
            }

            if (!anyStripped)
            {
                result.Add(original);
                continue;
            }

            // All contents stripped → drop the message entirely (no empty messages forwarded to LLM).
            if (rebuiltContents is null || rebuiltContents.Count == 0)
            {
                continue;
            }

            ChatMessage rebuilt = new(original.Role, rebuiltContents)
            {
                AuthorName = original.AuthorName,
                MessageId = original.MessageId,
                RawRepresentation = original.RawRepresentation,
            };

            if (original.AdditionalProperties is not null)
            {
                rebuilt.AdditionalProperties = original.AdditionalProperties;
            }

            result.Add(rebuilt);
        }

        return result;
    }
}
