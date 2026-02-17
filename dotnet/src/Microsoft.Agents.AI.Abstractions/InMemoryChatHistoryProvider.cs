// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
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
public sealed class InMemoryChatHistoryProvider : ChatHistoryProvider<InMemoryChatHistoryProvider.State>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration options that control the provider's behavior, including state initialization,
    /// message reduction, and serialization settings. If <see langword="null"/>, default settings will be used.
    /// </param>
    public InMemoryChatHistoryProvider(InMemoryChatHistoryProviderOptions? options = null)
        : base(
            options?.StateInitializer ?? (_ => new State()),
            options?.StateKey,
            options?.JsonSerializerOptions,
            options?.ProvideOutputMessageFilter,
            options?.StorageInputMessageFilter)
    {
        this.ChatReducer = options?.ChatReducer;
        this.ReducerTriggerEvent = options?.ReducerTriggerEvent ?? InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval;
    }

    /// <summary>
    /// Gets the chat reducer used to process or reduce chat messages. If null, no reduction logic will be applied.
    /// </summary>
    public IChatReducer? ChatReducer { get; }

    /// <summary>
    /// Gets the event that triggers the reducer invocation in this provider.
    /// </summary>
    public InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent ReducerTriggerEvent { get; }

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

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var state = this.GetOrInitializeState(context.Session);

        if (this.ReducerTriggerEvent is InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval && this.ChatReducer is not null)
        {
            state.Messages = (await this.ChatReducer.ReduceAsync(state.Messages, cancellationToken).ConfigureAwait(false)).ToList();
        }

        return state.Messages;
    }

    /// <inheritdoc />
    protected override async ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        var state = this.GetOrInitializeState(context.Session);

        // Add request and response messages to the provider
        var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);
        state.Messages.AddRange(allNewMessages);

        if (this.ReducerTriggerEvent is InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded && this.ChatReducer is not null)
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
        [JsonPropertyName("messages")]
        public List<ChatMessage> Messages { get; set; } = [];
    }
}
