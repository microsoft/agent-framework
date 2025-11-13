// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.AspNetCore.Components.AI;

// Roughly lifted from src/Libraries/Microsoft.Extensions.AI.Abstractions/ChatCompletion/ChatResponseExtensions.cs
internal static class MessageHelpers
{
    internal static void CoalesceContent(IList<AIContent> contents)
    {
        Coalesce<TextContent>(
            contents,
            mergeSingle: false,
            canMerge: null,
            static (contents, start, end) => new(MergeText(contents, start, end)) { AdditionalProperties = contents[start].AdditionalProperties?.Clone() });

        Coalesce(
            contents,
            mergeSingle: false,
            canMerge: static (r1, r2) => string.IsNullOrEmpty(r1.ProtectedData), // we allow merging if the first item has no ProtectedData, even if the second does
            static (contents, start, end) =>
            {
                TextReasoningContent content = new(MergeText(contents, start, end))
                {
                    AdditionalProperties = contents[start].AdditionalProperties?.Clone()
                };

#if DEBUG
                for (int i = start; i < end - 1; i++)
                {
                    Debug.Assert(contents[i] is TextReasoningContent { ProtectedData: null }, "Expected all but the last to have a null ProtectedData");
                }
#endif

                if (((TextReasoningContent)contents[end - 1]).ProtectedData is { } protectedData)
                {
                    content.ProtectedData = protectedData;
                }

                return content;
            });

        Coalesce(
            contents,
            mergeSingle: false,
            canMerge: static (r1, r2) => r1.MediaType == r2.MediaType && r1.HasTopLevelMediaType("text") && r1.Name == r2.Name,
            static (contents, start, end) =>
            {
                Debug.Assert(end - start > 1, "Expected multiple contents to merge");

                MemoryStream ms = new();
                for (int i = start; i < end; i++)
                {
                    var current = (DataContent)contents[i];
#if NET
                    ms.Write(current.Data.Span);
#else
                    if (!MemoryMarshal.TryGetArray(current.Data, out var segment))
                    {
                        segment = new(current.Data.ToArray());
                    }

                    ms.Write(segment.Array!, segment.Offset, segment.Count);
#endif
                }

                var first = (DataContent)contents[start];
                return new DataContent(new ReadOnlyMemory<byte>(ms.GetBuffer(), 0, (int)ms.Length), first.MediaType) { Name = first.Name };
            });

        Coalesce(
            contents,
            mergeSingle: true,
            canMerge: static (r1, r2) => r1.CallId == r2.CallId,
            static (contents, start, end) =>
            {
                var firstContent = (CodeInterpreterToolCallContent)contents[start];

                if (start == end - 1)
                {
                    if (firstContent.Inputs is not null)
                    {
                        CoalesceContent(firstContent.Inputs);
                    }

                    return firstContent;
                }

                List<AIContent>? inputs = null;

                for (int i = start; i < end; i++)
                {
                    (inputs ??= []).AddRange(((CodeInterpreterToolCallContent)contents[i]).Inputs ?? []);
                }

                if (inputs is not null)
                {
                    CoalesceContent(inputs);
                }

                return new()
                {
                    CallId = firstContent.CallId,
                    Inputs = inputs,
                    AdditionalProperties = firstContent.AdditionalProperties?.Clone(),
                };
            });

        Coalesce(
            contents,
            mergeSingle: true,
            canMerge: static (r1, r2) => r1.CallId is not null && r2.CallId is not null && r1.CallId == r2.CallId,
            static (contents, start, end) =>
            {
                var firstContent = (CodeInterpreterToolResultContent)contents[start];

                if (start == end - 1)
                {
                    if (firstContent.Outputs is not null)
                    {
                        CoalesceContent(firstContent.Outputs);
                    }

                    return firstContent;
                }

                List<AIContent>? output = null;

                for (int i = start; i < end; i++)
                {
                    (output ??= []).AddRange(((CodeInterpreterToolResultContent)contents[i]).Outputs ?? []);
                }

                if (output is not null)
                {
                    CoalesceContent(output);
                }

                return new()
                {
                    CallId = firstContent.CallId,
                    Outputs = output,
                    AdditionalProperties = firstContent.AdditionalProperties?.Clone(),
                };
            });

        static string MergeText(IList<AIContent> contents, int start, int end)
        {
            Debug.Assert(end - start > 1, "Expected multiple contents to merge");

            StringBuilder sb = new();
            for (int i = start; i < end; i++)
            {
                _ = sb.Append(contents[i]);
            }

            return sb.ToString();
        }

        static void Coalesce<TContent>(
            IList<AIContent> contents,
            bool mergeSingle,
            Func<TContent, TContent, bool>? canMerge,
            Func<IList<AIContent>, int, int, TContent> merge)
            where TContent : AIContent
        {
            // Iterate through all of the items in the list looking for contiguous items that can be coalesced.
            int start = 0;
            while (start < contents.Count)
            {
                if (!TryAsCoalescable(contents[start], out var firstContent))
                {
                    start++;
                    continue;
                }

                // Iterate until we find a non-coalescable item.
                int i = start + 1;
                TContent prev = firstContent;
                while (i < contents.Count && TryAsCoalescable(contents[i], out TContent? next) && (canMerge is null || canMerge(prev, next)))
                {
                    i++;
                    prev = next;
                }

                // If there's only one item in the run, and we don't want to merge single items, skip it.
                if (start == i - 1 && !mergeSingle)
                {
                    start++;
                    continue;
                }

                // Store the replacement node and null out all of the nodes that we coalesced.
                // We can then remove all coalesced nodes in one O(N) operation via RemoveAll.
                // Leave start positioned at the start of the next run.
                contents[start] = merge(contents, start, i);

                start++;
                while (start < i)
                {
                    contents[start++] = null!;
                }

                static bool TryAsCoalescable(AIContent content, [NotNullWhen(true)] out TContent? coalescable)
                {
                    if (content is TContent tmp && tmp.Annotations is not { Count: > 0 })
                    {
                        coalescable = tmp;
                        return true;
                    }

                    coalescable = null;
                    return false;
                }
            }

            // Remove all of the null slots left over from the coalescing process.
            RemoveNullContents(contents);
        }
    }

    private static void RemoveNullContents<T>(IList<T> contents)
        where T : class
    {
        if (contents is List<AIContent> contentsList)
        {
            _ = contentsList.RemoveAll(u => u is null);
        }
        else
        {
            int nextSlot = 0;
            int contentsCount = contents.Count;
            for (int i = 0; i < contentsCount; i++)
            {
                if (contents[i] is { } content)
                {
                    contents[nextSlot++] = content;
                }
            }

            for (int i = contentsCount - 1; i >= nextSlot; i--)
            {
                contents.RemoveAt(i);
            }

            Debug.Assert(nextSlot == contents.Count, "Expected final count to equal list length.");
        }
    }

    internal static bool ProcessUpdate(ChatResponseUpdate update, List<ChatMessage> messages, ILogger? logger = null)
    {
        // If there is no message created yet, or if the last update we saw had a different
        // identifying parts, create a new message.
        bool isNewMessage = true;
        if (messages.Count != 0)
        {
            var lastMessage = messages[messages.Count - 1];
            isNewMessage =
                NotEmptyOrEqual(update.AuthorName, lastMessage.AuthorName) ||
                NotEmptyOrEqual(update.MessageId, lastMessage.MessageId) ||
                NotNullOrEqual(update.Role, lastMessage.Role);

            logger?.LogDebug(
                "ProcessUpdate checking: update.MessageId={UpdateMessageId}, lastMessage.MessageId={LastMessageId}, isNewMessage={IsNew}",
                update.MessageId, lastMessage.MessageId, isNewMessage);
        }

        // Get the message to target, either a new one or the last ones.
        ChatMessage message;
        if (isNewMessage)
        {
            message = new(ChatRole.Assistant, []);
            messages.Add(message);
            logger?.LogDebug("ProcessUpdate: Created new message, total count={Count}", messages.Count);
        }
        else
        {
            message = messages[messages.Count - 1];
        }

        // Some members on ChatResponseUpdate map to members of ChatMessage.
        // Incorporate those into the latest message; in cases where the message
        // stores a single value, prefer the latest update's value over anything
        // stored in the message.

        if (update.AuthorName is not null)
        {
            message.AuthorName = update.AuthorName;
        }

        if (message.CreatedAt is null || (update.CreatedAt is not null && update.CreatedAt > message.CreatedAt))
        {
            message.CreatedAt = update.CreatedAt;
        }

        if (update.Role is ChatRole role)
        {
            message.Role = role;
        }

        if (update.MessageId is { Length: > 0 })
        {
            // Note that this must come after the message checks earlier, as they depend
            // on this value for change detection.
            var oldId = message.MessageId;
            message.MessageId = update.MessageId;
            logger?.LogDebug("ProcessUpdate: Set MessageId from {OldId} to {NewId}", oldId, update.MessageId);
        }

        foreach (var content in update.Contents)
        {
            message.Contents.Add(content);
            logger?.LogDebug("ProcessUpdate: Added content type {ContentType}", content.GetType().Name);
        }

        return isNewMessage;
    }

    /// <summary>Gets whether both strings are not null/empty and not the same as each other.</summary>
    private static bool NotEmptyOrEqual(string? s1, string? s2) =>
        s1 is { Length: > 0 } str1 && s2 is { Length: > 0 } str2 && str1 != str2;

    /// <summary>Gets whether two roles are not null and not the same as each other.</summary>
    private static bool NotNullOrEqual(ChatRole? r1, ChatRole? r2) =>
        r1.HasValue && r2.HasValue && r1.Value != r2.Value;
}
