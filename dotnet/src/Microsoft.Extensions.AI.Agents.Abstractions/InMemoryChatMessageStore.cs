// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an in-memory store for chat messages associated with a specific thread.
/// </summary>
internal class InMemoryChatMessageStore : IList<ChatMessage>, IChatMessageStore
{
    private readonly List<ChatMessage> _messages = new();

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
    public Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(messages);
        this._messages.AddRange(messages);
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
    {
        return Task.FromResult<IEnumerable<ChatMessage>>(this._messages);
    }

    /// <inheritdoc />
    public ValueTask DeserializeStateAsync(JsonElement? serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (serializedStoreState is null)
        {
            return new ValueTask();
        }

        var state = JsonSerializer.Deserialize(
            serializedStoreState.Value,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState))) as StoreState;

        if (state?.Messages is { Count: > 0 } messages)
        {
            this._messages.AddRange(messages);
        }

        return new ValueTask();
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

    internal class StoreState
    {
        public IList<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
    }
}
