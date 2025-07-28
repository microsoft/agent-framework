// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines methods for storing and retrieving chat messages associated with a specific thread.
/// </summary>
/// <remarks>
/// Implementations of this interface are responsible for managing the storage of chat messages,
/// including handling large volumes of data by truncating or summarizing messages as necessary.
/// </remarks>
public interface IChatMessageStore
{
    /// <summary>
    /// Gets all the messages from the store that should be used for the next agent invocation.
    /// </summary>
    /// <param name="threadId">An optional thread id to retrieve messages for. A store may not support storing multiple threads, in which case null may be provided.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <exception cref="InvalidOperationException">No thread id was provided, but the store requires one to function.</exception>
    /// <returns>A collection of chat messages.</returns>
    /// <remarks>
    /// <para>
    /// Messages are returned in ascending chronological order, with the oldest message first.
    /// </para>
    /// <para>
    /// If the messages stored in the store become very large, it is up to the store to
    /// truncate, summarize or otherwise limit the number of messages returned.
    /// </para>
    /// <para>
    /// The output id from <see cref="AddMessagesAsync(string?, IReadOnlyCollection{ChatMessage}, CancellationToken)"/> should be used here to retrieve messages for the same thread.
    /// If null was returned, null can be passed as input here.
    /// </para>
    /// </remarks>
    Task<ICollection<ChatMessage>> GetMessagesAsync(string? threadId, CancellationToken cancellationToken);

    /// <summary>
    /// Adds messages to the store.
    /// </summary>
    /// <param name="threadId">Thread id to store messages for or null if the store will create the id on first add.</param>
    /// <param name="messages">The messages to add.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The thread id that the messages were stored for.</returns>
    /// <remarks>
    /// This method may return null if the store does not support storing multiple threads.
    /// </remarks>
    Task<string?> AddMessagesAsync(string? threadId, IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken);

#if NETCOREAPP3_0_OR_GREATER
    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this store.
    /// </summary>
    /// <param name="stateElement">A <see cref="JsonElement"/> representing the state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <remarks>
    /// This method, together with <see cref="SerializeAsync(JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    Task DeserializeAsync(JsonElement? stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => Task.CompletedTask;

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    /// <remarks>
    /// This method, together with <see cref="DeserializeAsync(JsonElement?, JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    Task<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => Task.FromResult<JsonElement?>(null);

#else
    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this store.
    /// </summary>
    /// <param name="stateElement">A <see cref="JsonElement"/> representing the state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <remarks>
    /// This method, together with <see cref="SerializeAsync(JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    Task DeserializeAsync(JsonElement? stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    /// <remarks>
    /// This method, together with <see cref="DeserializeAsync(JsonElement?, JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    Task<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default);
#endif
}
