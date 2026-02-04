// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for an <see cref="AgentSession"/> that maintain all chat history in local memory.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="InMemoryAgentSession"/> is designed for scenarios where chat history should be stored locally
/// rather than in external services or databases. This approach provides high performance and simplicity while
/// maintaining full control over the conversation data.
/// </para>
/// <para>
/// In-memory threads do not persist conversation data across application restarts
/// unless explicitly serialized and restored.
/// </para>
/// </remarks>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public abstract class InMemoryAgentSession : AgentSession
{
    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentSession"/> class.
    /// </summary>
    /// <param name="chatHistoryProvider">
    /// An optional <see cref="InMemoryChatHistoryProvider"/> instance to use for storing chat messages.
    /// If <see langword="null"/>, a new empty <see cref="InMemoryChatHistoryProvider"/> will be created.
    /// </param>
    /// <remarks>
    /// This constructor allows sharing of <see cref="ChatHistoryProvider"/> between sessions or providing pre-configured
    /// <see cref="ChatHistoryProvider"/> with specific reduction or processing logic.
    /// </remarks>
    protected InMemoryAgentSession(InMemoryChatHistoryProvider? chatHistoryProvider = null)
    {
        this.ChatHistoryProvider = chatHistoryProvider ?? [];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentSession"/> class.
    /// </summary>
    /// <param name="messages">The initial messages to populate the conversation history.</param>
    /// <exception cref="ArgumentNullException"><paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor is useful for initializing sessions with existing conversation history or
    /// for migrating conversations from other storage systems.
    /// </remarks>
    protected InMemoryAgentSession(IEnumerable<ChatMessage> messages)
    {
        this.ChatHistoryProvider = [.. messages];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="InMemoryAgentSession"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the session.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="chatHistoryProviderFactory">
    /// Optional factory function to create the <see cref="InMemoryChatHistoryProvider"/> from its serialized state.
    /// If not provided, a default factory will be used that creates a basic <see cref="InMemoryChatHistoryProvider"/>.
    /// </param>
    /// <exception cref="ArgumentException">The <paramref name="serializedState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedState"/> is invalid or cannot be deserialized to the expected type.</exception>
    /// <remarks>
    /// This constructor enables restoration of in-memory threads from previously saved state, allowing
    /// conversations to be resumed across application restarts or migrated between different instances.
    /// </remarks>
    protected InMemoryAgentSession(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        Func<JsonElement, JsonSerializerOptions?, InMemoryChatHistoryProvider>? chatHistoryProviderFactory = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var state = serializedState.Deserialize(
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(InMemoryAgentSessionState))) as InMemoryAgentSessionState;

        this.ChatHistoryProvider =
            chatHistoryProviderFactory?.Invoke(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions) ??
            new InMemoryChatHistoryProvider(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions);
    }

    /// <summary>
    /// Gets or sets the <see cref="InMemoryChatHistoryProvider"/> used by this thread.
    /// </summary>
    public InMemoryChatHistoryProvider ChatHistoryProvider { get; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    protected internal virtual JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var chatHistoryProviderState = this.ChatHistoryProvider.Serialize(jsonSerializerOptions);

        var state = new InMemoryAgentSessionState
        {
            ChatHistoryProviderState = chatHistoryProviderState,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(InMemoryAgentSessionState)));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey) ?? this.ChatHistoryProvider?.GetService(serviceType, serviceKey);

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay => $"Count = {this.ChatHistoryProvider.Count}";

    internal sealed class InMemoryAgentSessionState
    {
        public JsonElement? ChatHistoryProviderState { get; set; }
    }
}
