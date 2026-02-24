// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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

    /// <summary>
    /// Gets or sets a value indicating whether the executor should automatically send the <see cref="TurnToken"/>
    /// after returning from <see cref="ChatProtocolExecutor.TakeTurnAsync(List{ChatMessage}, IWorkflowContext, bool?, CancellationToken)"/>
    /// </summary>
    public bool AutoSendTurnToken { get; set; } = true;
}

/// <summary>
/// Provides a base class for executors that implement the Agent Workflow Chat Protocol.
/// This executor maintains a list of chat messages and processes them when a turn is taken.
/// </summary>
public abstract class ChatProtocolExecutor : StatefulExecutor<List<ChatMessage>>
{
    internal static readonly Func<List<ChatMessage>> s_initFunction = () => [];
    private readonly ChatProtocolExecutorOptions _options;

    private static readonly StatefulExecutorOptions s_baseExecutorOptions = new()
    {
        AutoSendMessageHandlerResultObject = false,
        AutoYieldOutputHandlerResultObject = false
    };

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatProtocolExecutor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier for this executor instance. Cannot be null or empty.</param>
    /// <param name="options">Optional configuration settings for the executor. If null, default options are used.</param>
    /// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
    protected ChatProtocolExecutor(string id, ChatProtocolExecutorOptions? options = null, bool declareCrossRunShareable = false)
        : base(id, () => [], s_baseExecutorOptions, declareCrossRunShareable)
    {
        this._options = options ?? new();
    }

    /// <summary>
    /// Gets a value indicating whether string-based messages are supported by this <see cref="ChatProtocolExecutor"/>.
    /// </summary>
    [MemberNotNullWhen(true, nameof(StringMessageChatRole))]
    protected bool SupportsStringMessage => this.StringMessageChatRole.HasValue;

    /// <inheritdoc cref="ChatProtocolExecutorOptions.StringMessageChatRole"/>
    protected ChatRole? StringMessageChatRole => this._options.StringMessageChatRole;

    /// <inheritdoc cref="ChatProtocolExecutorOptions.AutoSendTurnToken"/>
    protected bool AutoSendTurnToken => this._options.AutoSendTurnToken;

    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return protocolBuilder.ConfigureRoutes(ConfigureRoutes)
                              .SendsMessage<List<ChatMessage>>()
                              .SendsMessage<TurnToken>();

        void ConfigureRoutes(RouteBuilder routeBuilder)
        {
            if (this.SupportsStringMessage)
            {
                routeBuilder = routeBuilder.AddHandler<string>(
                    (message, context) => this.AddMessageAsync(new(this.StringMessageChatRole.Value, message), context));
            }

            routeBuilder.AddHandler<ChatMessage>(this.AddMessageAsync)
                        .AddHandler<IEnumerable<ChatMessage>>(this.AddMessagesAsync)
                        .AddHandler<ChatMessage[]>(this.AddMessagesAsync)
                        //.AddHandler<List<ChatMessage>>(this.AddMessagesAsync)
                        .AddHandler<TurnToken>(this.TakeTurnAsync);
        }
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

            if (this.AutoSendTurnToken)
            {
                await context.SendMessageAsync(token, cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            // Rerun the initialStateFactory to reset the state to empty list. (We could return the empty list directly,
            // but this is more consistent if the initial state factory becomes more complex.)
            return s_initFunction();
        }
    }

    /// <summary>
    /// Processes the current set of turn messages using the specified asynchronous processing function.
    /// </summary>
    /// <remarks>If the provided list of chat messages is null, an initial empty list is supplied to the
    /// processing function. If the processing function returns null, an empty list is used as the result.</remarks>
    /// <param name="processFunc">A delegate that asynchronously processes a list of chat messages within the given workflow context and
    /// cancellation token, returning the processed list of chat messages or null.</param>
    /// <param name="context">The workflow context in which the messages are processed.</param>
    /// <param name="cancellationToken">A token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A ValueTask that represents the asynchronous operation. The result contains the processed list of chat messages,
    /// or an empty list if the processing function returns null.</returns>
    protected ValueTask ProcessTurnMessagesAsync(Func<List<ChatMessage>, IWorkflowContext, CancellationToken, ValueTask<List<ChatMessage>?>> processFunc, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return this.InvokeWithStateAsync(InvokeProcessFuncAsync, context, cancellationToken: cancellationToken);

        async ValueTask<List<ChatMessage>?> InvokeProcessFuncAsync(List<ChatMessage>? maybePendingMessages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            return (await processFunc(maybePendingMessages ?? s_initFunction(), context, cancellationToken).ConfigureAwait(false))
                ?? s_initFunction();
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
