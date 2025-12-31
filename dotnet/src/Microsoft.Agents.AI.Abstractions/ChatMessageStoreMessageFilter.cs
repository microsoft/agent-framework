// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="ChatMessageStore"/> decorator that allows filtering the messages
/// passed into and out of an inner <see cref="ChatMessageStore"/>.
/// </summary>
public sealed class ChatMessageStoreMessageFilter : ChatMessageStore
{
    private readonly ChatMessageStore _innerChatMessageStore;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? _invokingMessagesFilter;
    private readonly Func<InvokedContext, InvokedContext>? _invokedMessagesFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatMessageStoreMessageFilter"/> class.
    /// </summary>
    /// <remarks>Use this constructor to customize how messages are filtered before and after invocation by
    /// providing appropriate filter functions. If no filters are provided, the message store operates without
    /// additional filtering.</remarks>
    /// <param name="innerChatMessageStore">The underlying chat message store to be wrapped. Cannot be null.</param>
    /// <param name="invokingMessagesFilter">An optional filter function to apply to messages before they are invoked. If null, no filter is applied at this
    /// stage.</param>
    /// <param name="invokedMessagesFilter">An optional filter function to apply to the invocation context after messages have been invoked. If null, no
    /// filter is applied at this stage.</param>
    /// <exception cref="ArgumentNullException">Thrown if innerChatMessageStore is null.</exception>
    public ChatMessageStoreMessageFilter(
        ChatMessageStore innerChatMessageStore,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? invokingMessagesFilter = null,
        Func<InvokedContext, InvokedContext>? invokedMessagesFilter = null)
    {
        this._innerChatMessageStore = Throw.IfNull(innerChatMessageStore);

        if (invokingMessagesFilter == null && invokedMessagesFilter == null)
        {
            throw new ArgumentException("At least one filter function, invokingMessagesFilter or invokedMessagesFilter, must be provided.");
        }

        this._invokingMessagesFilter = invokingMessagesFilter;
        this._invokedMessagesFilter = invokedMessagesFilter;
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var messages = await this._innerChatMessageStore.InvokingAsync(context, cancellationToken).ConfigureAwait(false);
        return this._invokingMessagesFilter != null ? this._invokingMessagesFilter(messages) : messages;
    }

    /// <inheritdoc />
    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (this._invokedMessagesFilter != null)
        {
            context = this._invokedMessagesFilter(context);
        }

        return this._innerChatMessageStore.InvokedAsync(context, cancellationToken);
    }

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return this._innerChatMessageStore.Serialize(jsonSerializerOptions);
    }
}
