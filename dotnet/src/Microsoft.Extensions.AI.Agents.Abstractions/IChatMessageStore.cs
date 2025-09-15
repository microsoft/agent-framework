// Copyright (c) Microsoft. All rights reserved.

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
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
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
    /// When using implementations of <see cref="IChatMessageStore"/>, a new one should be created for each thread
    /// since they may contain state that is specific to a thread.
    /// </para>
    /// </remarks>
    Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Adds messages to the store.
    /// </summary>
    /// <param name="messages">The messages to add.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task.</returns>
    Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default);

    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this store.
    /// </summary>
    /// <param name="serializedStoreState">A <see cref="JsonElement"/> representing the state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> that completes when the state has been deserialized.</returns>
    /// <remarks>
    /// This method, together with <see cref="SerializeStateAsync(JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    ValueTask DeserializeStateAsync(JsonElement? serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    /// <remarks>
    /// This method, together with <see cref="DeserializeStateAsync(JsonElement?, JsonSerializerOptions?, CancellationToken)"/> can be used to save and load messages from a persistent store
    /// if this store only has messages in memory.
    /// </remarks>
    ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default);
}
