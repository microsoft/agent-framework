// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal class ChatProtocolExecutorOptions
{
    public ChatRole? StringMessageChatRole { get; set; }
}

// TODO: Make this a public type (in a later PR; todo: make an issue)
internal abstract class ChatProtocolExecutor : StatefulExecutor<List<ChatMessage>>
{
    private readonly static Func<List<ChatMessage>> s_initFunction = () => [];
    private readonly ChatRole? _stringMessageChatRole;

    internal ChatProtocolExecutor(string id, ChatProtocolExecutorOptions? options = null, bool declareCrossRunShareable = false)
        : base(id, () => [], declareCrossRunShareable: declareCrossRunShareable)
    {
        this._stringMessageChatRole = options?.StringMessageChatRole;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        if (this._stringMessageChatRole.HasValue)
        {
            routeBuilder = routeBuilder.AddHandler<string>(
                (message, context) => this.AddMessageAsync(new(this._stringMessageChatRole.Value, message), context));
        }

        return routeBuilder.AddHandler<ChatMessage>(this.AddMessageAsync)
                           .AddHandler<IEnumerable<ChatMessage>>(this.AddMessagesAsync)
                           .AddHandler<ChatMessage[]>(this.AddMessagesAsync)
                           .AddHandler<List<ChatMessage>>(this.AddMessagesAsync)
                           .AddHandler<TurnToken>(this.TakeTurnAsync);
    }

    protected ValueTask AddMessageAsync(ChatMessage message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.InvokeWithStateAsync(ForwardMessageAsync, context, cancellationToken: cancellationToken);

        ValueTask<List<ChatMessage>?> ForwardMessageAsync(List<ChatMessage>? maybePendingMessages, IWorkflowContext context, CancellationToken cancelationToken)
        {
            maybePendingMessages ??= s_initFunction();
            maybePendingMessages.Add(message);
            return new(maybePendingMessages);
        }
    }

    protected ValueTask AddMessagesAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.InvokeWithStateAsync(ForwardMessageAsync, context, cancellationToken: cancellationToken);

        ValueTask<List<ChatMessage>?> ForwardMessageAsync(List<ChatMessage>? maybePendingMessages, IWorkflowContext context, CancellationToken cancelationToken)
        {
            maybePendingMessages ??= s_initFunction();
            maybePendingMessages.AddRange(messages);
            return new(maybePendingMessages);
        }
    }

    public ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.InvokeWithStateAsync(InvokeTakeTurnAsync, context, cancellationToken: cancellationToken);

        async ValueTask<List<ChatMessage>?> InvokeTakeTurnAsync(List<ChatMessage>? maybePendingMessages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await this.TakeTurnAsync(maybePendingMessages ?? s_initFunction(), context, token.EmitEvents, cancellationToken)
                      .ConfigureAwait(false);

            await context.SendMessageAsync(token, cancellationToken: cancellationToken).ConfigureAwait(false);

            // Rerun the initialStateFactory to reset the state to empty list. (We could return the empty list directly,
            // but this is more consistent if the initial state factory becomes more complex.)
            return s_initFunction();
        }
    }

    protected abstract ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default);
}
