// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
public class AgentThread
{
    /// <summary>
    /// Gets or sets the id of the current thread.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This id may be null if the thread has no id, or
    /// if it represents a service-owned thread but the service
    /// has not yet been called to create the thread.
    /// </para>
    /// <para>
    /// The id may also change over time where the <see cref="AgentThread"/>
    /// is a proxy to a service owned thread that forks on each agent invocation.
    /// </para>
    /// </remarks>
    public string? Id { get; set; }

    /// <summary>
    /// This method is called when new messages have been contributed to the chat by any participant.
    /// </summary>
    /// <remarks>
    /// Inheritors can use this method to update their context based on the new message.
    /// </remarks>
    /// <param name="newMessages">The new messages.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    protected internal virtual Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }
}
