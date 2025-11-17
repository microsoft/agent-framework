// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides configuration options for <see cref="ChatProtocolExecutor"/>.
/// </summary>
public class ChatProtocolExecutorOptions
{
    /// <summary>
    /// Gets or sets the chat role to use when converting string messages to <see cref="ChatMessage"/> instances.
    /// If set, the executor will accept string messages and convert them to chat messages with this role.
    /// </summary>
    public ChatRole? StringMessageChatRole { get; set; }
}

/// <summary>
/// Provides a base class for executors that implement the Agent Workflow Chat Protocol.
/// This executor maintains a list of chat messages and processes them when a turn is taken.
/// </summary>
public abstract class ChatProtocolExecutor : StatefulExecutor<List<ChatMessage>>
{
    private static readonly Func<List<ChatMessage>> s_initFunction = () => [];
    private readonly ChatRole? _stringMessageChatRole;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatProtocolExecutor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier for this executor instance. Cannot be null or empty.</param>
    /// <param name="options">Optional configuration settings for the executor. If null, default options are used.</param>
    /// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
    protected ChatProtocolExecutor(string id, ChatProtocolExecutorOptions? options = null, bool declareCrossRunShareable = false)
        : base(id, () => [], declareCrossRunShareable: declareCrossRunShareable)
    {
        this._stringMessageChatRole = options?.StringMessageChatRole;
    }

    /// <inheritdoc/>
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

    /// <summary>
    /// Adds a single chat message to the accumulated messages for the current turn.
    /// </summary>
    /// <param name="message">The chat message to add.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
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

    /// <summary>
    /// Adds multiple chat messages to the accumulated messages for the current turn.
    /// </summary>
    /// <param name="messages">The collection of chat messages to add.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
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

    /// <summary>
    /// Handles a turn token by processing all accumulated chat messages and then resetting the message state.
    /// </summary>
    /// <param name="token">The turn token that triggers message processing.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
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

    /// <summary>
    /// When overridden in a derived class, processes the accumulated chat messages for a single turn.
    /// </summary>
    /// <param name="messages">The list of chat messages accumulated since the last turn.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <param name="emitEvents">Indicates whether events should be emitted during processing. If null, the default behavior is used.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    protected abstract ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default);
}
