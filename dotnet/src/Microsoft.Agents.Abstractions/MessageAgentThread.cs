// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// An abstract base class for agent threads that can produce all chat history for agent invocation on each invocation.
/// </summary>
/// <remarks>
/// <para>
/// Some agents need to be invoked with all relevant chat history messages in order to produce a result, while some must be invoked
/// with the id of a server side thread that contains the chat history.
/// </para>
/// <para>
/// This abstract base class is the base class for all thread types that support the case where the agent is invoked with messages.
/// Implementations must consider the size of the messages provided, so that they do not exceed the maximum size of the context window
/// of the agent they are used with. Where appropriate, implementations should truncate or summarize messages so that the size of messages
/// are constrained.
/// </para>
/// </remarks>
public abstract class MessageAgentThread : AgentThread
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
    public abstract IAsyncEnumerable<ChatMessage> GetMessagesAsync(CancellationToken cancellationToken = default);

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        Throw.IfNull(serviceType);

        return
            serviceKey is null && serviceType == typeof(MessageAgentThread) ? this :
            base.GetService(serviceType, serviceKey);
    }
}
