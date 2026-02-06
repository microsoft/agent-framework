// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an in-memory implementation of <see cref="ChatHistoryProvider"/> with support for message reduction.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="InMemoryChatHistoryProvider"/> stores chat messages in the <see cref="AgentSession.StateBag"/>,
/// providing fast access and manipulation capabilities integrated with session state management.
/// </para>
/// <para>
/// This <see cref="ChatHistoryProvider"/> maintains all messages in memory. For long-running conversations or high-volume scenarios, consider using
/// message reduction strategies or alternative storage implementations.
/// </para>
/// </remarks>
public sealed class InMemoryChatHistoryProvider : ChatHistoryProvider
{
    private const string DefaultStateBagKey = "InMemoryChatHistoryProvider.State";

    private readonly string _stateKey;
    private readonly Func<AgentSession?, State> _stateInitializer;

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="stateInitializer">
    /// An optional delegate that initializes the provider state on the first invocation.
    /// If <see langword="null"/>, a default initializer that creates an empty state will be used.
    /// </param>
    /// <param name="chatReducer">
    /// An optional <see cref="IChatReducer"/> instance used to process, reduce, or optimize chat messages.
    /// This can be used to implement strategies like message summarization, truncation, or cleanup.
    /// </param>
    /// <param name="reducerTriggerEvent">
    /// Specifies when the message reducer should be invoked. The default is <see cref="ChatReducerTriggerEvent.BeforeMessagesRetrieval"/>,
    /// which applies reduction logic when messages are retrieved for agent consumption.
    /// </param>
    /// <param name="stateKey">
    /// An optional key to use for storing the state in the <see cref="AgentSession.StateBag"/>.
    /// If <see langword="null"/>, a default key will be used.
    /// </param>
    /// <remarks>
    /// Message reducers enable automatic management of message storage by implementing strategies to
    /// keep memory usage under control while preserving important conversation context.
    /// </remarks>
    public InMemoryChatHistoryProvider(
        Func<AgentSession?, State>? stateInitializer = null,
        IChatReducer? chatReducer = null,
        ChatReducerTriggerEvent reducerTriggerEvent = ChatReducerTriggerEvent.BeforeMessagesRetrieval,
        string? stateKey = null)
    {
        this._stateInitializer = stateInitializer ?? (_ => new State());
        this.ChatReducer = chatReducer;
        this.ReducerTriggerEvent = reducerTriggerEvent;
        this._stateKey = stateKey ?? DefaultStateBagKey;
    }

    /// <summary>
    /// Gets the chat reducer used to process or reduce chat messages. If null, no reduction logic will be applied.
    /// </summary>
    public IChatReducer? ChatReducer { get; }

    /// <summary>
    /// Gets the event that triggers the reducer invocation in this provider.
    /// </summary>
    public ChatReducerTriggerEvent ReducerTriggerEvent { get; }

    /// <summary>
    /// Gets the chat messages stored for the specified session.
    /// </summary>
    /// <param name="session">The agent session containing the state.</param>
    /// <returns>A list of chat messages, or an empty list if no state is found.</returns>
    public List<ChatMessage> GetMessages(AgentSession? session)
        => this.GetOrInitializeState(session).Messages;

    /// <summary>
    /// Sets the chat messages for the specified session.
    /// </summary>
    /// <param name="session">The agent session containing the state.</param>
    /// <param name="messages">The messages to store.</param>
    /// <exception cref="ArgumentNullException"><paramref name="messages"/> is <see langword="null"/>.</exception>
    public void SetMessages(AgentSession? session, List<ChatMessage> messages)
    {
        _ = Throw.IfNull(messages);

        var state = this.GetOrInitializeState(session);
        state.Messages = messages;
    }

    /// <summary>
    /// Gets the state from the session's StateBag, or initializes it using the state initializer if not present.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <returns>The provider state, or null if no session is available.</returns>
    private State GetOrInitializeState(AgentSession? session)
    {
        var state = session?.StateBag.GetValue<State>(this._stateKey, AgentAbstractionsJsonUtilities.DefaultOptions);
        if (state is not null)
        {
            return state;
        }

        state = this._stateInitializer(session);
        if (session is not null)
        {
            session.StateBag.SetValue(this._stateKey, state, AgentAbstractionsJsonUtilities.DefaultOptions);
        }

        return state;
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        var state = this.GetOrInitializeState(context.Session);

        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.BeforeMessagesRetrieval && this.ChatReducer is not null)
        {
            state.Messages = (await this.ChatReducer.ReduceAsync(state.Messages, cancellationToken).ConfigureAwait(false)).ToList();
        }

        return state.Messages;
    }

    /// <inheritdoc />
    public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        if (context.InvokeException is not null)
        {
            return;
        }

        var state = this.GetOrInitializeState(context.Session);

        // Add request, AI context provider, and response messages to the provider
        var allNewMessages = context.RequestMessages.Concat(context.AIContextProviderMessages ?? []).Concat(context.ResponseMessages ?? []);
        state.Messages.AddRange(allNewMessages);

        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.AfterMessageAdded && this.ChatReducer is not null)
        {
            state.Messages = (await this.ChatReducer.ReduceAsync(state.Messages, cancellationToken).ConfigureAwait(false)).ToList();
        }
    }

    /// <summary>
    /// Represents the state of a <see cref="InMemoryChatHistoryProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Gets or sets the list of chat messages.
        /// </summary>
        public List<ChatMessage> Messages { get; set; } = [];
    }

    /// <summary>
    /// Defines the events that can trigger a reducer in the <see cref="InMemoryChatHistoryProvider"/>.
    /// </summary>
    public enum ChatReducerTriggerEvent
    {
        /// <summary>
        /// Trigger the reducer when a new message is added.
        /// <see cref="InvokedAsync(InvokedContext, CancellationToken)"/> will only complete when reducer processing is done.
        /// </summary>
        AfterMessageAdded,

        /// <summary>
        /// Trigger the reducer before messages are retrieved from the provider.
        /// The reducer will process the messages before they are returned to the caller.
        /// </summary>
        BeforeMessagesRetrieval
    }
}
