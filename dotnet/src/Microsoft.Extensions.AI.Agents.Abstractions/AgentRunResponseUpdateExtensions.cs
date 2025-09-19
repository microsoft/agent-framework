// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

#pragma warning disable S109 // Magic numbers should not be used
#pragma warning disable S1121 // Assignments should not be made from within sub-expressions

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides extension methods for working with <see cref="AgentRunResponseUpdate"/> instances.
/// </summary>
public static class AgentRunResponseUpdateExtensions
{
    /// <summary>Combines <see cref="AgentRunResponseUpdate"/> instances into a single <see cref="AgentRunResponse"/>.</summary>
    /// <param name="updates">The updates to be combined.</param>
    /// <returns>The combined <see cref="AgentRunResponse"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a single <see cref="AgentRunResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="AgentRunResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static AgentRunResponse ToAgentRunResponse(
        this IEnumerable<AgentRunResponseUpdate> updates)
    {
        _ = Throw.IfNull(updates);

        AgentRunResponse response = new();

        foreach (var update in updates)
        {
            ProcessUpdate(update, response);
        }

        FinalizeResponse(response);

        return response;
    }

    /// <summary>Combines <see cref="AgentRunResponseUpdate"/> instances into a single <see cref="AgentRunResponse"/>.</summary>
    /// <param name="updates">The updates to be combined.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The combined <see cref="AgentRunResponse"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a single <see cref="AgentRunResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="AgentRunResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static Task<AgentRunResponse> ToAgentRunResponseAsync(
        this IAsyncEnumerable<AgentRunResponseUpdate> updates,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(updates);

        return ToAgentRunResponseAsync(updates, cancellationToken);

        static async Task<AgentRunResponse> ToAgentRunResponseAsync(
            IAsyncEnumerable<AgentRunResponseUpdate> updates,
            CancellationToken cancellationToken)
        {
            AgentRunResponse response = new();

            await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                ProcessUpdate(update, response);
            }

            FinalizeResponse(response);

            return response;
        }
    }

    /// <summary>Coalesces sequential <see cref="AIContent"/> content elements.</summary>
    internal static void CoalesceTextContent(List<AIContent> contents)
    {
        Coalesce<TextContent>(contents, static text => new(text));
        Coalesce<TextReasoningContent>(contents, static text => new(text));

        // This implementation relies on TContent's ToString returning its exact text.
        static void Coalesce<TContent>(List<AIContent> contents, Func<string, TContent> fromText)
            where TContent : AIContent
        {
            StringBuilder? coalescedText = null;

            // Iterate through all of the items in the list looking for contiguous items that can be coalesced.
            int start = 0;
            while (start < contents.Count - 1)
            {
                // We need at least two TextContents in a row to be able to coalesce.
                if (contents[start] is not TContent firstText)
                {
                    start++;
                    continue;
                }

                if (contents[start + 1] is not TContent secondText)
                {
                    start += 2;
                    continue;
                }

                // Append the text from those nodes and continue appending subsequent TextContents until we run out.
                // We null out nodes as their text is appended so that we can later remove them all in one O(N) operation.
                coalescedText ??= new();
                _ = coalescedText.Clear().Append(firstText).Append(secondText);
                contents[start + 1] = null!;
                int i = start + 2;
                for (; i < contents.Count && contents[i] is TContent next; i++)
                {
                    _ = coalescedText.Append(next);
                    contents[i] = null!;
                }

                // Store the replacement node. We inherit the properties of the first text node. We don't
                // currently propagate additional properties from the subsequent nodes. If we ever need to,
                // we can add that here.
                var newContent = fromText(coalescedText.ToString());
                contents[start] = newContent;
                newContent.AdditionalProperties = firstText.AdditionalProperties?.Clone();

                start = i;
            }

            // Remove all of the null slots left over from the coalescing process.
            _ = contents.RemoveAll(u => u is null);
        }
    }

    /// <summary>Finalizes the <paramref name="response"/> object.</summary>
    private static void FinalizeResponse(AgentRunResponse response)
    {
        int count = response.Messages.Count;
        for (int i = 0; i < count; i++)
        {
            CoalesceTextContent((List<AIContent>)response.Messages[i].Contents);
        }
    }

    /// <summary>Processes the <see cref="AgentRunResponseUpdate"/>, incorporating its contents into <paramref name="response"/>.</summary>
    /// <param name="update">The update to process.</param>
    /// <param name="response">The <see cref="AgentRunResponse"/> object that should be updated based on <paramref name="update"/>.</param>
    private static void ProcessUpdate(AgentRunResponseUpdate update, AgentRunResponse response)
    {
        // If there is no message created yet, or if the last update we saw had a different
        // message ID or role than the newest update, create a new message.
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
        else if (update.Role is { } updateRole
            && response.Messages[response.Messages.Count - 1].Role is { } lastRole
            && updateRole != lastRole)
        {
            isNewMessage = true;
        }

        if (isNewMessage)
        {
            message = new ChatMessage(ChatRole.Assistant, []);
            response.Messages.Add(message);
        }
        else
        {
            message = response.Messages[response.Messages.Count - 1];
        }

        // Some members on AgentRunResponseUpdate map to members of ChatMessage.
        // Incorporate those into the latest message; in cases where the message
        // stores a single value, prefer the latest update's value over anything
        // stored in the message.
        if (update.AuthorName is not null)
        {
            message.AuthorName = update.AuthorName;
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

        // Other members on a AgentRunResponseUpdate map to members of the AgentRunResponse.
        // Update the response object with those, preferring the values from later updates.

        if (update.AgentId is { Length: > 0 })
        {
            response.AgentId = update.AgentId;
        }

        if (update.ResponseId is { Length: > 0 })
        {
            response.ResponseId = update.ResponseId;
        }

        if (update.CreatedAt is not null)
        {
            response.CreatedAt = update.CreatedAt;
        }

        if (update.AdditionalProperties is not null)
        {
            if (response.AdditionalProperties is null)
            {
                response.AdditionalProperties = new(update.AdditionalProperties);
            }
            else
            {
                foreach (var item in update.AdditionalProperties)
                {
                    response.AdditionalProperties[item.Key] = item.Value;
                }
            }
        }
    }
}
