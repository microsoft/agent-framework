// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an in-memory implementation of <see cref="ChatHistoryProvider"/> with support for message reduction and collection semantics.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="InMemoryChatHistoryProvider"/> stores chat messages entirely in local memory, providing fast access and manipulation
/// capabilities. It implements both <see cref="ChatHistoryProvider"/> for agent integration and <see cref="IList{ChatMessage}"/>
/// for direct collection manipulation.
/// </para>
/// <para>
/// This <see cref="ChatHistoryProvider"/> maintains all messages in memory. For long-running conversations or high-volume scenarios, consider using
/// message reduction strategies or alternative storage implementations.
/// </para>
/// </remarks>
[DebuggerDisplay("Count = {Count}")]
[DebuggerTypeProxy(typeof(DebugView))]
public sealed class InMemoryChatHistoryProvider : ChatHistoryProvider, IList<ChatMessage>, IReadOnlyList<ChatMessage>
{
    private List<ChatMessage> _messages;

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class.
    /// </summary>
    /// <remarks>
    /// This constructor creates a basic in-memory <see cref="ChatHistoryProvider"/> without message reduction capabilities.
    /// Messages will be stored exactly as added without any automatic processing or reduction.
    /// </remarks>
    public InMemoryChatHistoryProvider()
    {
        this._messages = [];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the provider.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedState"/> is not a valid JSON object or cannot be deserialized.</exception>
    /// <remarks>
    /// This constructor enables restoration of messages from previously saved state, allowing
    /// conversation history to be preserved across application restarts or migrated between instances.
    /// </remarks>
    public InMemoryChatHistoryProvider(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
        : this(null, serializedState, jsonSerializerOptions, ChatReducerTriggerEvent.BeforeMessagesRetrieval)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="chatReducer">
    /// A <see cref="IChatReducer"/> instance used to process, reduce, or optimize chat messages.
    /// This can be used to implement strategies like message summarization, truncation, or cleanup.
    /// </param>
    /// <param name="reducerTriggerEvent">
    /// Specifies when the message reducer should be invoked. The default is <see cref="ChatReducerTriggerEvent.BeforeMessagesRetrieval"/>,
    /// which applies reduction logic when messages are retrieved for agent consumption.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="chatReducer"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// Message reducers enable automatic management of message storage by implementing strategies to
    /// keep memory usage under control while preserving important conversation context.
    /// </remarks>
    public InMemoryChatHistoryProvider(IChatReducer chatReducer, ChatReducerTriggerEvent reducerTriggerEvent = ChatReducerTriggerEvent.BeforeMessagesRetrieval)
        : this(chatReducer, default, null, reducerTriggerEvent)
    {
        Throw.IfNull(chatReducer);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatHistoryProvider"/> class, with an existing state from a serialized JSON element.
    /// </summary>
    /// <param name="chatReducer">An optional <see cref="IChatReducer"/> instance used to process or reduce chat messages. If null, no reduction logic will be applied.</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the provider.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="reducerTriggerEvent">The event that should trigger the reducer invocation.</param>
    public InMemoryChatHistoryProvider(IChatReducer? chatReducer, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, ChatReducerTriggerEvent reducerTriggerEvent = ChatReducerTriggerEvent.BeforeMessagesRetrieval)
    {
        this.ChatReducer = chatReducer;
        this.ReducerTriggerEvent = reducerTriggerEvent;

        if (serializedState.ValueKind is JsonValueKind.Object)
        {
            var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
            var state = serializedState.Deserialize(
                jso.GetTypeInfo(typeof(State))) as State;
            if (state?.Messages is { } messages)
            {
                this._messages = messages;
                return;
            }
        }

        this._messages = [];
    }

    /// <summary>
    /// Gets the chat reducer used to process or reduce chat messages. If null, no reduction logic will be applied.
    /// </summary>
    public IChatReducer? ChatReducer { get; }

    /// <summary>
    /// Gets the event that triggers the reducer invocation in this provider.
    /// </summary>
    public ChatReducerTriggerEvent ReducerTriggerEvent { get; }

    /// <inheritdoc />
    public int Count => this._messages.Count;

    /// <inheritdoc />
    public bool IsReadOnly => ((IList)this._messages).IsReadOnly;

    /// <inheritdoc />
    public ChatMessage this[int index]
    {
        get => this._messages[index];
        set => this._messages[index] = value;
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.BeforeMessagesRetrieval && this.ChatReducer is not null)
        {
            this._messages = (await this.ChatReducer.ReduceAsync(this._messages, cancellationToken).ConfigureAwait(false)).ToList();
        }

        return this._messages;
    }

    /// <inheritdoc />
    public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        if (context.InvokeException is not null)
        {
            return;
        }

        // Add request, AI context provider, and response messages to the provider
        var allNewMessages = context.RequestMessages.Concat(context.AIContextProviderMessages ?? []).Concat(context.ResponseMessages ?? []);
        this._messages.AddRange(allNewMessages);

        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.AfterMessageAdded && this.ChatReducer is not null)
        {
            this._messages = (await this.ChatReducer.ReduceAsync(this._messages, cancellationToken).ConfigureAwait(false)).ToList();
        }
    }

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        State state = new()
        {
            Messages = this._messages,
        };

        var jso = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(state, jso.GetTypeInfo(typeof(State)));
    }

    /// <inheritdoc />
    public int IndexOf(ChatMessage item)
        => this._messages.IndexOf(item);

    /// <inheritdoc />
    public void Insert(int index, ChatMessage item)
        => this._messages.Insert(index, item);

    /// <inheritdoc />
    public void RemoveAt(int index)
        => this._messages.RemoveAt(index);

    /// <inheritdoc />
    public void Add(ChatMessage item)
        => this._messages.Add(item);

    /// <inheritdoc />
    public void Clear()
        => this._messages.Clear();

    /// <inheritdoc />
    public bool Contains(ChatMessage item)
        => this._messages.Contains(item);

    /// <inheritdoc />
    public void CopyTo(ChatMessage[] array, int arrayIndex)
        => this._messages.CopyTo(array, arrayIndex);

    /// <inheritdoc />
    public bool Remove(ChatMessage item)
        => this._messages.Remove(item);

    /// <inheritdoc />
    public IEnumerator<ChatMessage> GetEnumerator()
        => this._messages.GetEnumerator();

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator()
        => this.GetEnumerator();

    internal sealed class State
    {
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

    private sealed class DebugView(InMemoryChatHistoryProvider provider)
    {
        [DebuggerBrowsable(DebuggerBrowsableState.RootHidden)]
        public ChatMessage[] Items => provider._messages.ToArray();
    }
}
