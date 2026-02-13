// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
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
public sealed class InMemoryChatHistoryProvider : ChatHistoryProvider
{
    private static IEnumerable<ChatMessage> DefaultExcludeChatHistoryFilter(IEnumerable<ChatMessage> messages)
        => messages.Where(m => m.GetAgentRequestMessageSourceType() != AgentRequestMessageSourceType.ChatHistory);

    private readonly string _stateKey;
    private readonly Func<AgentSession?, State> _stateInitializer;
    private readonly JsonSerializerOptions _jsonSerializerOptions;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _storageInputMessageFilter;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? _retrievalOutputMessageFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration options that control the provider's behavior, including state initialization,
    /// message reduction, and serialization settings. If <see langword="null"/>, default settings will be used.
    /// </param>
    public InMemoryChatHistoryProvider(InMemoryChatHistoryProviderOptions? options = null)
    {
        this._stateInitializer = options?.StateInitializer ?? (_ => new State());
        this.ChatReducer = options?.ChatReducer;
        this.ReducerTriggerEvent = options?.ReducerTriggerEvent ?? InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval;
        this._stateKey = options?.StateKey ?? base.StateKey;
        this._jsonSerializerOptions = options?.JsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
        this._storageInputMessageFilter = options?.StorageInputMessageFilter ?? DefaultExcludeChatHistoryFilter;
        this._retrievalOutputMessageFilter = options?.RetrievalOutputMessageFilter;
    }

    /// <inheritdoc />
    public override string StateKey => this._stateKey;

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

    /// <summary>
    /// Gets the state from the session's StateBag, or initializes it using the state initializer if not present.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <returns>The provider state, or null if no session is available.</returns>
    private State GetOrInitializeState(AgentSession? session)
    {
        if (session?.StateBag.TryGetValue<State>(this._stateKey, out var state, this._jsonSerializerOptions) is true && state is not null)
        {
            return state;
        }

        state = this._stateInitializer(session);
        if (session is not null)
        {
            session.StateBag.SetValue(this._stateKey, state, this._jsonSerializerOptions);
        }

        return state;
    }

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        var state = this.GetOrInitializeState(context.Session);

        if (this.ReducerTriggerEvent is InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.BeforeMessagesRetrieval && this.ChatReducer is not null)
        {
            state.Messages = (await this.ChatReducer.ReduceAsync(state.Messages, cancellationToken).ConfigureAwait(false)).ToList();
        }

        IEnumerable<ChatMessage> output = state.Messages;
        if (this._retrievalOutputMessageFilter is not null)
        {
            output = this._retrievalOutputMessageFilter(output);
        }
        return output
            .Select(message => message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, this.GetType().FullName!))
            .Concat(context.RequestMessages);
    }

    /// <inheritdoc />
    protected override async ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        if (context.InvokeException is not null)
        {
            return;
        }

        var state = this.GetOrInitializeState(context.Session);

        // Add request and response messages to the provider
        var allNewMessages = this._storageInputMessageFilter(context.RequestMessages).Concat(context.ResponseMessages ?? []);
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
