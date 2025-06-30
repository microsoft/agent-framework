// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// An interface for agent threads that allow retrieval of messages in the thread for agent invocation.
/// </summary>
/// <remarks>
/// <para>
/// Some agents need to be invoked with all relevant chat history messages in order to produce a result, while some must be invoked
/// with the id of a server side thread that contains the chat history.
/// </para>
/// <para>
/// This interface can be implemented by all thread types that support the case where the agent is invoked with the chat history.
/// Implementations must consider the size of the messages provided, so that they do not exceed the maximum size of the context window
/// of the agent they are used with. Where appropriate, implementations should truncate or summarize messages so that the size of messages
/// are constrained.
/// </para>
/// </remarks>
public interface IMessagesRetrievableThread
{
    /// <summary>
    /// Asynchronously retrieves all messages to be used for the agent invocation.
    /// </summary>
    /// <remarks>
    /// Messages are returned in ascending chronological order.
    /// </remarks>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The messages in the thread.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    IAsyncEnumerable<ChatMessage> GetMessagesAsync(CancellationToken cancellationToken = default);
}
