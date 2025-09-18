// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// A base class for agent threads that operate entirely in memory without external storage.
/// </summary>
public abstract class InMemoryAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class.
    /// </summary>
    /// <param name="messageStore">An optional <see cref="InMemoryChatMessageStore"/> to use for storing chat messages. If null, a new instance will be created.</param>
    protected InMemoryAgentThread(InMemoryChatMessageStore? messageStore = null)
    {
        this.MessageStore = messageStore ?? new InMemoryChatMessageStore();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class with the specified initial messages.
    /// </summary>
    /// <param name="messages">The messages to initialize the thread with.</param>
    protected InMemoryAgentThread(IEnumerable<ChatMessage> messages)
    {
        this.MessageStore = new InMemoryChatMessageStore();
        foreach (var message in messages)
        {
            this.MessageStore.Add(message);
        }
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="messageStoreFactory">A factory function to create the <see cref="InMemoryChatMessageStore"/> from its serialized state.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedThreadState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedThreadState"/> is invalid or cannot be deserialized to the expected type.</exception>
    protected InMemoryAgentThread(
        JsonElement serializedThreadState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        Func<JsonElement, JsonSerializerOptions?, InMemoryChatMessageStore>? messageStoreFactory = null)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(InMemoryAgentThreadState))) as InMemoryAgentThreadState;

        this.MessageStore =
            messageStoreFactory?.Invoke(state?.StoreState ?? default, jsonSerializerOptions) ??
            new InMemoryChatMessageStore(state?.StoreState ?? default, jsonSerializerOptions);
    }

    /// <summary>
    /// Gets or sets the <see cref="InMemoryChatMessageStore"/> used by this thread.
    /// </summary>
    public InMemoryChatMessageStore MessageStore { get; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        var storeState = await this.MessageStore.SerializeStateAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false);

        var state = new InMemoryAgentThreadState
        {
            StoreState = storeState,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(InMemoryAgentThreadState)));
    }

    /// <inheritdoc />
    protected internal override Task MessagesReceivedAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
        => this.MessageStore.AddMessagesAsync(newMessages, cancellationToken);

    internal sealed class InMemoryAgentThreadState
    {
        public JsonElement? StoreState { get; set; }
    }
}
