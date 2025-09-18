// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an in-memory store for chat messages associated with a specific thread.
/// </summary>
public sealed class InMemoryChatMessageStore : IList<ChatMessage>, IChatMessageStore
{
    private List<ChatMessage> _messages;

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatMessageStore"/> class.
    /// </summary>
    public InMemoryChatMessageStore()
    {
        this._messages = [];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatMessageStore"/> class, with an existing state from a serialized JSON element.
    /// </summary>
    /// <param name="serializedStoreState">A <see cref="JsonElement"/> representing the serialized state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    public InMemoryChatMessageStore(JsonElement serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null)
        : this(null, serializedStoreState, jsonSerializerOptions, ChatReducerTriggerEvent.BeforeMessagesRetrieval)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatMessageStore"/> class.
    /// </summary>
    /// <param name="chatReducer">An optional <see cref="IChatReducer"/> instance used to process or reduce chat messages. If null, no reduction logic will be applied.</param>
    /// <param name="reducerTriggerEvent">The event that should trigger the reducer invocation.</param>
    public InMemoryChatMessageStore(IChatReducer chatReducer, ChatReducerTriggerEvent reducerTriggerEvent = ChatReducerTriggerEvent.BeforeMessagesRetrieval)
        : this(chatReducer, default, null, reducerTriggerEvent)
    {
        Throw.IfNull(chatReducer);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryChatMessageStore"/> class, with an existing state from a serialized JSON element.
    /// </summary>
    /// <param name="chatReducer">An optional <see cref="IChatReducer"/> instance used to process or reduce chat messages. If null, no reduction logic will be applied.</param>
    /// <param name="serializedStoreState">A <see cref="JsonElement"/> representing the serialized state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="reducerTriggerEvent">The event that should trigger the reducer invocation.</param>
    public InMemoryChatMessageStore(IChatReducer? chatReducer, JsonElement serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, ChatReducerTriggerEvent reducerTriggerEvent = ChatReducerTriggerEvent.BeforeMessagesRetrieval)
    {
        this.ChatReducer = chatReducer;
        this.ReducerTriggerEvent = reducerTriggerEvent;

        if (serializedStoreState.ValueKind is JsonValueKind.Object)
        {
            var state = serializedStoreState.Deserialize(
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState))) as StoreState;
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
    /// Gets the event that triggers the reducer invocation in this store.
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
    public async Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(messages);

        this._messages.AddRange(messages);

        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.AfterMessageAdded && this.ChatReducer is not null)
        {
            this._messages = (await this.ChatReducer.ReduceAsync(this._messages, cancellationToken).ConfigureAwait(false)).ToList();
        }
    }

    /// <inheritdoc />
    public async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
    {
        if (this.ReducerTriggerEvent is ChatReducerTriggerEvent.BeforeMessagesRetrieval && this.ChatReducer is not null)
        {
            this._messages = (await this.ChatReducer.ReduceAsync(this._messages, cancellationToken).ConfigureAwait(false)).ToList();
        }

        return this._messages;
    }

    /// <inheritdoc />
    public ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        StoreState state = new()
        {
            Messages = this._messages,
        };

        return new ValueTask<JsonElement?>(JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState))));
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

    internal sealed class StoreState
    {
        public List<ChatMessage> Messages { get; set; } = [];
    }

    /// <summary>
    /// Defines the events that can trigger a reducer in the <see cref="InMemoryChatMessageStore"/>.
    /// </summary>
    public enum ChatReducerTriggerEvent
    {
        /// <summary>
        /// Trigger the reducer when a new message is added.
        /// <see cref="AddMessagesAsync(IEnumerable{ChatMessage}, CancellationToken)"/> will only complete when reducer processing is done.
        /// </summary>
        AfterMessageAdded,

        /// <summary>
        /// Trigger the reducer before messages are retrieved from the store.
        /// The reducer will process the messages before they are returned to the caller.
        /// </summary>
        BeforeMessagesRetrieval
    }
}
