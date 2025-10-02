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
/// Provides an abstract base class for storing and managing chat messages associated with agent conversations.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="ChatMessageStore"/> defines the contract for persistent storage of chat messages in agent conversations.
/// Implementations are responsible for managing message persistence, retrieval, and any necessary optimization
/// strategies such as truncation, summarization, or archival.
/// </para>
/// <para>
/// Key responsibilities include:
/// <list type="bullet">
/// <item><description>Storing chat messages with proper ordering and metadata preservation</description></item>
/// <item><description>Retrieving messages in chronological order for agent context</description></item>
/// <item><description>Managing storage limits through truncation, summarization, or other strategies</description></item>
/// <item><description>Supporting serialization for thread persistence and migration</description></item>
/// </list>
/// </para>
/// </remarks>
public abstract class ChatMessageStore
{
    /// <summary>
    /// Asynchronously retrieves all messages from the store that should be provided as context for the next agent invocation.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains a collection of <see cref="ChatMessage"/>
    /// instances in ascending chronological order (oldest first).
    /// </returns>
    /// <remarks>
    /// <para>
    /// Messages are returned in chronological order to maintain proper conversation flow and context for the agent.
    /// The oldest messages appear first in the collection, followed by more recent messages.
    /// </para>
    /// <para>
    /// If the total message history becomes very large, implementations should apply appropriate strategies to manage
    /// storage constraints, such as:
    /// <list type="bullet">
    /// <item><description>Truncating older messages while preserving recent context</description></item>
    /// <item><description>Summarizing message groups to maintain essential context</description></item>
    /// <item><description>Implementing sliding window approaches for message retention</description></item>
    /// <item><description>Archiving old messages while keeping active conversation context</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// Each store instance should be associated with a single conversation thread to ensure proper message isolation
    /// and context management.
    /// </para>
    /// </remarks>
    public abstract Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Asynchronously adds new messages to the store.
    /// </summary>
    /// <param name="messages">The collection of chat messages to add to the store.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous add operation.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// Messages should be added in the order they were generated to maintain proper chronological sequence.
    /// The store is responsible for preserving message ordering and ensuring that subsequent calls to
    /// <see cref="GetMessagesAsync"/> return messages in the correct chronological order.
    /// </para>
    /// <para>
    /// Implementations may perform additional processing during message addition, such as:
    /// <list type="bullet">
    /// <item><description>Validating message content and metadata</description></item>
    /// <item><description>Applying storage optimizations or compression</description></item>
    /// <item><description>Triggering background maintenance operations</description></item>
    /// <item><description>Updating indices or search capabilities</description></item>
    /// </list>
    /// </para>
    /// </remarks>
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
