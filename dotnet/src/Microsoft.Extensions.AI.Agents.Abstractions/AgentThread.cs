// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
public abstract class AgentThread
{
    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(default(JsonElement));
    }

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
