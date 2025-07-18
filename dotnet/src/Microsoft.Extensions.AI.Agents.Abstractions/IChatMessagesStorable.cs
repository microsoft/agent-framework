// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
public interface IChatMessagesStorable
{
    /// <summary>
    /// Gets all the messages from the store that should be used for the next agent invocation.
    /// </summary>
    /// <param name="threadId">Thread id to retrieve messages for.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A collection of chat messages.</returns>
    /// <remarks>
    /// If the messages stored in the store become very large, it is up to the store to
    /// trucate, summarize or otherwise limit the number of messages returned.
    /// </remarks>
    Task<ICollection<ChatMessage>> GetMessagesAsync(string threadId, CancellationToken cancellationToken);

    /// <summary>
    /// Adds messages to the store.
    /// </summary>
    /// <param name="threadId">Thread id to store messages for or null if the store will create the id on first add.</param>
    /// <param name="messages">The messages to add.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The thread id that the messages were stored for.</returns>
    Task<string> AddMessagesAsync(string? threadId, IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken);
}
