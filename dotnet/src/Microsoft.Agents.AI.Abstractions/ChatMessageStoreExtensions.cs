// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods for the <see cref="ChatMessageStore"/> class.
/// </summary>
public static class ChatMessageStoreExtensions
{
    /// <summary>
    /// Adds message filtering to an existing store, so that messages passed to the store and messages produced by the store
    /// can be filtered, updated or replaced.
    /// </summary>
    /// <param name="store">The store to add the message filter to.</param>
    /// <param name="invokingMessagesFilter">An optional filter function to apply to messages produced by the store. If null, no filter is applied at this
    /// stage.</param>
    /// <param name="invokedMessagesFilter">An optional filter function to apply to the invoked context messages before they are passed to the store. If null, no
    /// filter is applied at this stage.</param>
    /// <returns>The <see cref="ChatMessageStore"/> with filtering applied.</returns>
    public static ChatMessageStore WithMessageFilters(
        this ChatMessageStore store,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? invokingMessagesFilter = null,
        Func<ChatMessageStore.InvokedContext, ChatMessageStore.InvokedContext>? invokedMessagesFilter = null)
    {
        return new ChatMessageStoreMessageFilter(
            innerChatMessageStore: store,
            invokingMessagesFilter: invokingMessagesFilter,
            invokedMessagesFilter: invokedMessagesFilter);
    }

    /// <summary>
    /// Decorates the provided chat message store so that it does not store messages produced by any <see cref="AIContextProvider"/>.
    /// </summary>
    /// <param name="store">The store to add the message filter to.</param>
    /// <returns>A new <see cref="ChatMessageStore"/> instance that filters out <see cref="AIContextProvider"/> messages so they do not get stored.</returns>
    public static ChatMessageStore WithAIContextProviderMessageRemoval(this ChatMessageStore store)
    {
        return new ChatMessageStoreMessageFilter(
            innerChatMessageStore: store,
            invokedMessagesFilter: (ctx) =>
            {
                ctx.AIContextProviderMessages = null;
                return ctx;
            });
    }
}
