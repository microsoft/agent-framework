// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents;

/// <summary>
/// A base abstraction for storing conversations.
/// </summary>
public abstract class ConversationStore
{
    /// <summary>
    /// Adds the provided messages to the conversation store under the specified thread ID.
    /// </summary>
    /// <param name="threadId">The unique identifier for the conversation thread.</param>
    /// <param name="messages">The messages to add to the conversation in storage.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    public abstract Task AddMessages(
        string threadId,
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves the most recent messages from storage saved under the specified thread ID.
    /// </summary>
    /// <remarks>
    /// This method returns the specified number of messages in chronological order.
    /// </remarks>
    /// <param name="threadId">The unique identifier of the conversation thread for which to retrieve messages.</param>
    /// <param name="limit">The maximum number of messages to retrieve. Must be a positive integer.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests. Optional; defaults to <see langword="default"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains a read-only collection of <see
    /// cref="ChatMessage"/> objects, ordered from most recent to oldest. The collection will be empty if no messages
    /// are available.</returns>
    public abstract Task<IReadOnlyCollection<ChatMessage>> GetRecentMessages(
        string threadId,
        int limit,
        CancellationToken cancellationToken = default);
}
