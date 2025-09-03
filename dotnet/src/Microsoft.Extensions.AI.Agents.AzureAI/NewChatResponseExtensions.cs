// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using Microsoft.Shared.Diagnostics;

#pragma warning disable S109 // Magic numbers should not be used
#pragma warning disable S1121 // Assignments should not be made from within sub-expressions

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for working with <see cref="ChatResponse"/> and <see cref="ChatResponseUpdate"/> instances.
/// </summary>
public static class NewChatResponseExtensions
{
    /// <summary>Adds all of the messages from <paramref name="response"/> into <paramref name="list"/>.</summary>
    /// <param name="list">The destination list to which the messages from <paramref name="response"/> should be added.</param>
    /// <param name="response">The response containing the messages to add.</param>
    /// <exception cref="ArgumentNullException"><paramref name="list"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public static void NewAddMessages(this IList<ChatMessage> list, ChatResponse response)
    {
        _ = Throw.IfNull(list);
        _ = Throw.IfNull(response);

        if (list is List<ChatMessage> listConcrete)
        {
            listConcrete.AddRange(response.Messages);
        }
        else
        {
            foreach (var message in response.Messages)
            {
                list.Add(message);
            }
        }
    }

    /// <summary>Converts the <paramref name="updates"/> into <see cref="ChatMessage"/> instances and adds them to <paramref name="list"/>.</summary>
    /// <param name="list">The destination list to which the newly constructed messages should be added.</param>
    /// <param name="updates">The <see cref="ChatResponseUpdate"/> instances to convert to messages and add to the list.</param>
    /// <exception cref="ArgumentNullException"><paramref name="list"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a series of <see cref="ChatMessage"/> instances, the
    /// method may use <see cref="ChatResponseUpdate.MessageId"/> to determine message boundaries, as well as coalesce
    /// contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static void NewAddMessages(this IList<ChatMessage> list, IEnumerable<ChatResponseUpdate> updates)
    {
        _ = Throw.IfNull(list);
        _ = Throw.IfNull(updates);

        if (updates is ICollection<ChatResponseUpdate> { Count: 0 })
        {
            return;
        }

        list.NewAddMessages(updates.NewToChatResponse());
    }

    /// <summary>Converts the <paramref name="update"/> into a <see cref="ChatMessage"/> instance and adds it to <paramref name="list"/>.</summary>
    /// <param name="list">The destination list to which the newly constructed message should be added.</param>
    /// <param name="update">The <see cref="ChatResponseUpdate"/> instance to convert to a message and add to the list.</param>
    /// <param name="filter">A predicate to filter which <see cref="AIContent"/> gets included in the message.</param>
    /// <exception cref="ArgumentNullException"><paramref name="list"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="update"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// If the <see cref="ChatResponseUpdate"/> has no content, or all its content gets excluded by <paramref name="filter"/>, then
    /// no <see cref="ChatMessage"/> will be added to the <paramref name="list"/>.
    /// </remarks>
    public static void NewAddMessages(this IList<ChatMessage> list, ChatResponseUpdate update, Func<AIContent, bool>? filter = null)
    {
        _ = Throw.IfNull(list);
        _ = Throw.IfNull(update);

        var contentsList = filter is null ? update.Contents : update.Contents.Where(filter).ToList();
        if (contentsList.Count > 0)
        {
            list.Add(new(update.Role ?? ChatRole.Assistant, contentsList)
            {
                AuthorName = update.AuthorName,
                CreatedAt = update.CreatedAt,
                RawRepresentation = update.RawRepresentation,
                AdditionalProperties = update.AdditionalProperties,
            });
        }
    }

    /// <summary>Converts the <paramref name="updates"/> into <see cref="ChatMessage"/> instances and adds them to <paramref name="list"/>.</summary>
    /// <param name="list">The list to which the newly constructed messages should be added.</param>
    /// <param name="updates">The <see cref="ChatResponseUpdate"/> instances to convert to messages and add to the list.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task"/> representing the completion of the operation.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="list"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a series of <see cref="ChatMessage"/> instances, tne
    /// method may use <see cref="ChatResponseUpdate.MessageId"/> to determine message boundaries, as well as coalesce
    /// contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static Task NewAddMessagesAsync(
        this IList<ChatMessage> list, IAsyncEnumerable<ChatResponseUpdate> updates, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(list);
        _ = Throw.IfNull(updates);

        return AddMessagesAsync(list, updates, cancellationToken);

        static async Task AddMessagesAsync(
            IList<ChatMessage> list, IAsyncEnumerable<ChatResponseUpdate> updates, CancellationToken cancellationToken) =>
            list.NewAddMessages(await updates.NewToChatResponseAsync(cancellationToken).ConfigureAwait(false));
    }

    /// <summary>Combines <see cref="ChatResponseUpdate"/> instances into a single <see cref="ChatResponse"/>.</summary>
    /// <param name="updates">The updates to be combined.</param>
    /// <returns>The combined <see cref="ChatResponse"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a single <see cref="ChatResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="ChatResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static ChatResponse NewToChatResponse(
        this IEnumerable<ChatResponseUpdate> updates)
    {
        _ = Throw.IfNull(updates);

        ChatResponse response = new();

        foreach (var update in updates)
        {
            ProcessUpdate(update, response);
        }

        FinalizeResponse(response);

        return response;
    }

    /// <summary>Combines <see cref="ChatResponseUpdate"/> instances into a single <see cref="ChatResponse"/>.</summary>
    /// <param name="updates">The updates to be combined.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The combined <see cref="ChatResponse"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a single <see cref="ChatResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="ChatResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static Task<ChatResponse> NewToChatResponseAsync(
        this IAsyncEnumerable<ChatResponseUpdate> updates, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(updates);

        return ToChatResponseAsync(updates, cancellationToken);

        static async Task<ChatResponse> ToChatResponseAsync(
            IAsyncEnumerable<ChatResponseUpdate> updates, CancellationToken cancellationToken)
        {
            ChatResponse response = new();

            await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                ProcessUpdate(update, response);
            }

            FinalizeResponse(response);

            return response;
        }
    }

    /// <summary>Coalesces sequential <see cref="AIContent"/> content elements.</summary>
    internal static void CoalesceTextContent(IList<AIContent> contents)
    {
        Coalesce<TextContent>(contents, mergeSingle: false, static (contents, start, end) =>
            new(MergeText(contents, start, end))
            {
                AdditionalProperties = contents[start].AdditionalProperties?.Clone()
            });

        Coalesce<TextReasoningContent>(contents, mergeSingle: false, static (contents, start, end) =>
            new(MergeText(contents, start, end))
            {
                AdditionalProperties = contents[start].AdditionalProperties?.Clone()
            });

        static string MergeText(IList<AIContent> contents, int start, int end)
        {
            StringBuilder sb = new();
            for (int i = start; i < end; i++)
            {
                _ = sb.Append(contents[i]);
            }

            return sb.ToString();
        }

        static void Coalesce<TContent>(IList<AIContent> contents, bool mergeSingle, Func<IList<AIContent>, int, int, TContent> merge)
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
                while (i < contents.Count && TryAsCoalescable(contents[i], out _))
                {
                    i++;
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
    }

    /// <summary>Finalizes the <paramref name="response"/> object.</summary>
    private static void FinalizeResponse(ChatResponse response)
    {
        int count = response.Messages.Count;
        for (int i = 0; i < count; i++)
        {
            CoalesceTextContent((List<AIContent>)response.Messages[i].Contents);
        }
    }

    /// <summary>Processes the <see cref="ChatResponseUpdate"/>, incorporating its contents into <paramref name="response"/>.</summary>
    /// <param name="update">The update to process.</param>
    /// <param name="response">The <see cref="ChatResponse"/> object that should be updated based on <paramref name="update"/>.</param>
    private static void ProcessUpdate(ChatResponseUpdate update, ChatResponse response)
    {
        // If there is no message created yet, or if the last update we saw had a different
        // message ID than the newest update, create a new message.
        ChatMessage message;
        var isNewMessage = false;
        if (response.Messages.Count == 0)
        {
            isNewMessage = true;
        }
        else if (update.MessageId is { Length: > 0 } updateMessageId
            && response.Messages[response.Messages.Count - 1].MessageId is string lastMessageId
            && updateMessageId != lastMessageId)
        {
            isNewMessage = true;
        }

        if (isNewMessage)
        {
            message = new(ChatRole.Assistant, []);
            response.Messages.Add(message);
        }
        else
        {
            message = response.Messages[response.Messages.Count - 1];
        }

        // Some members on ChatResponseUpdate map to members of ChatMessage.
        // Incorporate those into the latest message; in cases where the message
        // stores a single value, prefer the latest update's value over anything
        // stored in the message.

        if (update.AuthorName is not null)
        {
            message.AuthorName = update.AuthorName;
        }

        if (update.CreatedAt is not null)
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
            message.MessageId = update.MessageId;
        }

        foreach (var content in update.Contents)
        {
            switch (content)
            {
                // Usage content is treated specially and propagated to the response's Usage.
                case UsageContent usage:
                    (response.Usage ??= new()).Add(usage.Details);
                    break;

                default:
                    message.Contents.Add(content);
                    break;
            }
        }

        // Other members on a ChatResponseUpdate map to members of the ChatResponse.
        // Update the response object with those, preferring the values from later updates.

        if (update.ResponseId is { Length: > 0 })
        {
            response.ResponseId = update.ResponseId;
        }

        if (update.ConversationId is not null)
        {
            response.ConversationId = update.ConversationId;
        }

        if (update.CreatedAt is not null)
        {
            response.CreatedAt = update.CreatedAt;
        }

        if (update.FinishReason is not null)
        {
            response.FinishReason = update.FinishReason;
        }

        if (update.ModelId is not null)
        {
            response.ModelId = update.ModelId;
        }

        if (update.AdditionalProperties is not null)
        {
            if (response.AdditionalProperties is null)
            {
                response.AdditionalProperties = new(update.AdditionalProperties);
            }
            else
            {
                //response.AdditionalProperties.SetAll(update.AdditionalProperties);

                // TBD: Revert this temporary workaround when SetAll is available.
                foreach (var item in update.AdditionalProperties)
                {
                    response.AdditionalProperties[item.Key] = item.Value;
                }
            }
        }

        if (update.GetResponseStatus() is { } status)
        {
            response.SetResponseStatus(status);
        }
    }
}
