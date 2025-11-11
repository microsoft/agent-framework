// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides configuration options for <see cref="ChatForwardingExecutor"/>.
/// </summary>
public class ChatForwardingExecutorOptions
{
    /// <summary>
    /// Gets or sets the chat role to use when converting string messages to <see cref="ChatMessage"/> instances.
    /// If set, the executor will accept string messages and convert them to chat messages with this role.
    /// </summary>
    public ChatRole? StringMessageChatRole { get; set; }
}

/// <summary>
/// A ChatProtocol executor that forwards all messages it receives. Useful for splitting inputs into parallel
/// processing paths.
/// </summary>
/// <remarks>This executor is designed to be cross-run shareable and can be reset to its initial state. It handles
/// multiple chat-related types, enabling flexible message forwarding scenarios. Thread safety and reusability are
/// ensured by its design.</remarks>
/// <param name="id">The unique identifier for the executor instance. Used to distinguish this executor within the system.</param>
/// <param name="options">Optional configuration settings for the executor. If null, default options are used.</param>
public sealed class ChatForwardingExecutor(string id, ChatForwardingExecutorOptions? options = null) : Executor(id, declareCrossRunShareable: true), IResettableExecutor
{
    private readonly ChatRole? _stringMessageChatRole = options?.StringMessageChatRole;

    /// <inheritdoc/>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        if (this._stringMessageChatRole.HasValue)
        {
            routeBuilder = routeBuilder.AddHandler<string>(
                (message, context) => context.SendMessageAsync(new ChatMessage(ChatRole.User, message)));
        }

        return routeBuilder.AddHandler<ChatMessage>(ForwardMessageAsync)
                           .AddHandler<IEnumerable<ChatMessage>>(ForwardMessagesAsync)
                           .AddHandler<ChatMessage[]>(ForwardMessagesAsync)
                           .AddHandler<List<ChatMessage>>(ForwardMessagesAsync)
                           .AddHandler<TurnToken>(ForwardTurnTokenAsync);
    }

    private static ValueTask ForwardMessageAsync(ChatMessage message, IWorkflowContext context, CancellationToken cancellationToken)
        => context.SendMessageAsync(message, cancellationToken);

    // Note that this can be used to split a turn into multiple parallel turns taken, which will cause streaming ChatMessages
    // to overlap.
    private static ValueTask ForwardTurnTokenAsync(TurnToken message, IWorkflowContext context, CancellationToken cancellationToken)
        => context.SendMessageAsync(message, cancellationToken);

    // TODO: This is not ideal, but until we have a way of guaranteeing correct routing of interfaces across serialization
    // boundaries, we need to do type unification. It behaves better when used as a handler in ChatProtocolExecutor because
    // it is a strictly contravariant use, whereas this forces invariance on the type because it is directly forwarded.
    private static ValueTask ForwardMessagesAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
        => context.SendMessageAsync(messages is List<ChatMessage> messageList ? messageList : messages.ToList(), cancellationToken);

    private static ValueTask ForwardMessagesAsync(ChatMessage[] messages, IWorkflowContext context, CancellationToken cancellationToken)
        => context.SendMessageAsync(messages, cancellationToken);

    /// <inheritdoc/>
    public ValueTask ResetAsync() => default;
}
