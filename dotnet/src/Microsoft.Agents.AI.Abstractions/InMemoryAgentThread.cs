// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for agent threads that maintain all conversation state in local memory.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="InMemoryAgentThread"/> is designed for scenarios where conversation state should be stored locally
/// rather than in external services or databases. This approach provides high performance and simplicity while
/// maintaining full control over the conversation data.
/// </para>
/// <para>
/// In-memory threads do not persist conversation data across application restarts
/// unless explicitly serialized and restored.
/// </para>
/// </remarks>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public abstract class InMemoryAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class.
    /// </summary>
    /// <param name="messageStore">
    /// An optional <see cref="InMemoryChatMessageStore"/> instance to use for storing chat messages.
    /// If <see langword="null"/>, a new empty message store will be created.
    /// </param>
    /// <remarks>
    /// This constructor allows sharing of message stores between threads or providing pre-configured
    /// message stores with specific reduction or processing logic.
    /// </remarks>
    protected InMemoryAgentThread(InMemoryChatMessageStore? messageStore = null)
    {
        this.MessageStore = messageStore ?? [];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class.
    /// </summary>
    /// <param name="messages">The initial messages to populate the conversation history.</param>
    /// <exception cref="ArgumentNullException"><paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor is useful for initializing threads with existing conversation history or
    /// for migrating conversations from other storage systems.
    /// </remarks>
    protected InMemoryAgentThread(IEnumerable<ChatMessage> messages)
    {
        this.MessageStore = [.. messages];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentThread"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="messageStoreFactory">
    /// Optional factory function to create the <see cref="InMemoryChatMessageStore"/> from its serialized state.
    /// If not provided, a default factory will be used that creates a basic in-memory store.
    /// </param>
    /// <exception cref="ArgumentException">The <paramref name="serializedThreadState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedThreadState"/> is invalid or cannot be deserialized to the expected type.</exception>
    /// <remarks>
    /// This constructor enables restoration of in-memory threads from previously saved state, allowing
    /// conversations to be resumed across application restarts or migrated between different instances.
    /// </remarks>
    protected InMemoryAgentThread(
        JsonElement serializedThreadState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        Func<JsonElement, JsonSerializerOptions?, InMemoryChatMessageStore>? messageStoreFactory = null)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = serializedThreadState.Deserialize(
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
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var storeState = this.MessageStore.Serialize(jsonSerializerOptions);

        var state = new InMemoryAgentThreadState
        {
            StoreState = storeState,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(InMemoryAgentThreadState)));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey) ?? this.MessageStore?.GetService(serviceType, serviceKey);

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay => $"Count = {this.MessageStore.Count}";

    internal sealed class InMemoryAgentThreadState
    {
        public JsonElement? StoreState { get; set; }
    }
}
