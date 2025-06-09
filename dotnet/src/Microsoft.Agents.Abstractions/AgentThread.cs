// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
public class AgentThread
{
    /// <summary>
    /// Gets or sets the id of the current thread.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// This method is called when a new message has been contributed to the chat by any participant.
    /// </summary>
    /// <remarks>
    /// Inheritors can use this method to update their context based on the new message.
    /// </remarks>
    /// <param name="newMessage">The new message.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    protected internal virtual Task OnNewMessageAsync(ChatMessage newMessage, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }
}
