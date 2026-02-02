// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods for the <see cref="ChatHistoryProvider"/> class.
/// </summary>
public static class ChatHistoryProviderExtensions
{
    /// <summary>
    /// Adds message filtering to an existing <see cref="ChatHistoryProvider"/>, so that messages passed to the <see cref="ChatHistoryProvider"/> and messages
    /// provided by the <see cref="ChatHistoryProvider"/> can be filtered, updated or replaced.
    /// </summary>
    /// <param name="provider">The <see cref="ChatHistoryProvider"/> to add the message filter to.</param>
    /// <param name="invokingMessagesFilter">An optional filter function to apply to messages produced by the <see cref="ChatHistoryProvider"/>. If null, no filter is applied at this
    /// stage.</param>
    /// <param name="invokedMessagesFilter">An optional filter function to apply to the invoked context messages before they are passed to the <see cref="ChatHistoryProvider"/>. If null, no
    /// filter is applied at this stage.</param>
    /// <returns>The <see cref="ChatHistoryProvider"/> with filtering applied.</returns>
    public static ChatHistoryProvider WithMessageFilters(
        this ChatHistoryProvider provider,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? invokingMessagesFilter = null,
        Func<ChatHistoryProvider.InvokedContext, ChatHistoryProvider.InvokedContext>? invokedMessagesFilter = null)
    {
        return new ChatHistoryProviderMessageFilter(
            innerProvider: provider,
            invokingMessagesFilter: invokingMessagesFilter,
            invokedMessagesFilter: invokedMessagesFilter);
    }

    /// <summary>
    /// Decorates the provided chat message <see cref="ChatHistoryProvider"/> so that it does not add
    /// messages produced by any <see cref="AIContextProvider"/> to chat history.
    /// </summary>
    /// <param name="provider">The <see cref="ChatHistoryProvider"/> to add the message filter to.</param>
    /// <returns>A new <see cref="ChatHistoryProvider"/> instance that filters out <see cref="AIContextProvider"/> messages so they do not get added.</returns>
    public static ChatHistoryProvider WithAIContextProviderMessageRemoval(this ChatHistoryProvider provider)
    {
        return new ChatHistoryProviderMessageFilter(
            innerProvider: provider,
            invokedMessagesFilter: (ctx) =>
            {
                ctx.AIContextProviderMessages = null;
                return ctx;
            });
    }
}
