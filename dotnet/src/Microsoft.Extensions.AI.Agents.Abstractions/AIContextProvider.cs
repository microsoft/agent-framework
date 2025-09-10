// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base class for all AI context providers.
/// </summary>
/// <remarks>
/// An AI context provider is a component that can be used to enhance the AI's context management.
/// It can listen to changes in the conversation, provide additional context to
/// the AI model just before invocation and supply additional tools for function invocation.
/// </remarks>
public abstract class AIContextProvider
{
    /// <summary>
    /// Called just before messages are added to the chat by any participant.
    /// </summary>
    /// <remarks>
    /// Inheritors can use this method to update their context based on the new message.
    /// </remarks>
    /// <param name="newMessages">The new messages.</param>
    /// <param name="agentThreadId">The ID of the <see cref="AgentThread"/>.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    public virtual Task MessagesAddingAsync(IReadOnlyCollection<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    /// <summary>
    /// Called just before the Model/Agent/etc. is invoked
    /// Implementers can load any additional context required at this time,
    /// and they should return any context that should be passed to the Model/Agent/etc.
    /// </summary>
    /// <param name="newMessages">The most recent messages that the Model/Agent/etc. is being invoked with.</param>
    /// <param name="agentThreadId">The ID of the <see cref="AgentThread"/>.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been rendered and returned.</returns>
    public abstract Task<AIContext> ModelInvokingAsync(IEnumerable<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    protected internal virtual Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(default(JsonElement));
    }

    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this object.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the state of the object.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> that completes when the state has been deserialized.</returns>
    protected internal virtual Task DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }
}
