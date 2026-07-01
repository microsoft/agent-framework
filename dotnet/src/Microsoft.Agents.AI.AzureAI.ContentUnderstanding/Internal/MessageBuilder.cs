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
    /// <summary>
    /// Rebuilds the message list with attachments removed.
    /// </summary>
    /// <param name="source">The original per-turn messages.</param>
    /// <param name="attachmentsToStrip">
    /// The set of attachment instances to remove. Stripping uses reference equality
    /// (see <see cref="GetReferenceComparer"/>): only the exact <see cref="AIContent"/>
    /// instances contained in this set are removed. Callers MUST pass the original
    /// instances taken from <paramref name="source"/>; cloned, copied, or
    /// deserialized instances will NOT be matched and would leak through to the LLM.
    /// </param>
    public static List<ChatMessage> BuildSanitizedMessages(
        IEnumerable<ChatMessage>? source,
        IReadOnlyCollection<AIContent> attachmentsToStrip)
    {
        List<ChatMessage> result = new();
        if (source is null)
        {
            return result;
        }

        // Enforce reference-equality stripping regardless of the comparer the caller used
        // to build the passed-in collection (see GetReferenceComparer / XML remarks above).
        HashSet<AIContent> strip = new(attachmentsToStrip, AIContentReferenceEqualityComparer.Instance);

        foreach (ChatMessage original in source)
        {
            if (original is null)
            {
                continue;
            }

            if (strip.Count == 0 || original.Contents is null || original.Contents.Count == 0)
            {
                result.Add(original);
                continue;
            }

            List<AIContent>? rebuiltContents = null;
            bool anyStripped = false;
            for (int i = 0; i < original.Contents.Count; i++)
            {
                AIContent c = original.Contents[i];
                if (strip.Contains(c))
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

    /// <summary>
    /// Returns a reference-equality comparer suitable for building the
    /// <c>attachmentsToStrip</c> set passed to <see cref="BuildSanitizedMessages"/>.
    /// Reference equality is intentional: only the exact instances collected from the
    /// current turn are stripped, avoiding accidental removal of distinct attachments
    /// whose contents happen to compare equal.
    /// </summary>
    public static IEqualityComparer<AIContent> GetReferenceComparer()
        => AIContentReferenceEqualityComparer.Instance;
}
