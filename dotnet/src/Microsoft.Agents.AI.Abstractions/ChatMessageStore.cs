// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Defines methods for storing and retrieving chat messages associated with a specific thread.
/// </summary>
/// <remarks>
/// Implementations of this interface are responsible for managing the storage of chat messages,
/// including handling large volumes of data by truncating or summarizing messages as necessary.
/// </remarks>
public abstract class ChatMessageStore
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
    /// When using implementations of <see cref="ChatMessageStore"/>, a new one should be created for each thread
    /// since they may contain state that is specific to a thread.
    /// </para>
    /// </remarks>
    public abstract Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Adds messages to the store.
    /// </summary>
    /// <param name="messages">The messages to add.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task.</returns>
    public abstract Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default);

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public abstract JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null);

    /// <summary>Asks the <see cref="ChatMessageStore"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="ChatMessageStore"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="ChatMessageStore"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="ChatMessageStore"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;
}
