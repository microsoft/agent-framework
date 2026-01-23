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
/// A <see cref="ChatHistoryProvider"/> decorator that allows filtering the messages
/// passed into and out of an inner <see cref="ChatHistoryProvider"/>.
/// </summary>
public sealed class ChatHistoryProviderMessageFilter : ChatHistoryProvider
{
    private readonly ChatHistoryProvider _innerProvider;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? _invokingMessagesFilter;
    private readonly Func<InvokedContext, InvokedContext>? _invokedMessagesFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryProviderMessageFilter"/> class.
    /// </summary>
    /// <remarks>Use this constructor to customize how messages are filtered before and after invocation by
    /// providing appropriate filter functions. If no filters are provided, the <see cref="ChatHistoryProvider"/> operates without
    /// additional filtering.</remarks>
    /// <param name="innerProvider">The underlying <see cref="ChatHistoryProvider"/> to be wrapped. Cannot be null.</param>
    /// <param name="invokingMessagesFilter">An optional filter function to apply to messages provided by the <see cref="ChatHistoryProvider"/>
    /// before they are used by the agent. If null, no filter is applied at this stage.</param>
    /// <param name="invokedMessagesFilter">An optional filter function to apply to the invocation context after messages have been produced. If null, no
    /// filter is applied at this stage.</param>
    /// <exception cref="ArgumentNullException">Thrown if <paramref name="innerProvider"/> is null.</exception>
    public ChatHistoryProviderMessageFilter(
        ChatHistoryProvider innerProvider,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? invokingMessagesFilter = null,
        Func<InvokedContext, InvokedContext>? invokedMessagesFilter = null)
    {
        this._innerProvider = Throw.IfNull(innerProvider);

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
        var messages = await this._innerProvider.InvokingAsync(context, cancellationToken).ConfigureAwait(false);
        return this._invokingMessagesFilter != null ? this._invokingMessagesFilter(messages) : messages;
    }

    /// <inheritdoc />
    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (this._invokedMessagesFilter != null)
        {
            context = this._invokedMessagesFilter(context);
        }

        return this._innerProvider.InvokedAsync(context, cancellationToken);
    }

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return this._innerProvider.Serialize(jsonSerializerOptions);
    }
}
