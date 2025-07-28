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
public class AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThread"/> class.
    /// </summary>
    public AgentThread()
    {
    }

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

    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this thread.
    /// </summary>
    /// <param name="stateElement">A <see cref="JsonElement"/> representing the state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public virtual Task DeserializeAsync(JsonElement stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        // Deserialize the first element as the thread ID.
        var state = JsonSerializer.Deserialize(
            stateElement,
            jsonSerializerOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        this.Id = state?.Id;

        return Task.CompletedTask;
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        var state = new ThreadState
        {
            Id = this.Id
        };

        return Task.FromResult(JsonSerializer.SerializeToElement(state, jsonSerializerOptions.GetTypeInfo(typeof(ThreadState))));
    }

    internal class ThreadState
    {
        public string? Id { get; set; }
    }
}
