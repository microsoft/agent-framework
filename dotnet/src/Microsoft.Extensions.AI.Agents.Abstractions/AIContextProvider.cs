// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// the Model/Agent/etc. just before invocation and supply additional function tools.
/// </remarks>
public abstract class AIContextProvider
{
    /// <summary>
    /// Called just before the Model/Agent/etc. is invoked
    /// Implementers can load any additional context required at this time,
    /// and they should return any context that should be passed to the Model/Agent/etc.
    /// </summary>
    /// <param name="context">Contains the event context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been rendered and returned.</returns>
    public abstract ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Called just before the Model/Agent/etc. is invoked
    /// Implementers can load any additional context required at this time,
    /// and they should return any context that should be passed to the Model/Agent/etc.
    /// </summary>
    /// <param name="context">Contains the event context.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been rendered and returned.</returns>
    public virtual ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        return default;
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual ValueTask<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return default;
    }

    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this object.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the state of the object.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ValueTask"/> that completes when the state has been deserialized.</returns>
    public virtual ValueTask DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return default;
    }

    /// <summary>
    /// Contains the event context provided to <see cref="InvokingAsync(InvokingContext, CancellationToken)"/>.
    /// </summary>
    public class InvokingContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokingContext"/> class.
        /// </summary>
        /// <param name="requestMessages">The messages to be sent to the Model/Agent/etc. for this invocation.</param>
        /// <exception cref="ArgumentNullException">Thrown if <paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokingContext(IEnumerable<ChatMessage> requestMessages)
        {
            RequestMessages = requestMessages ?? throw new ArgumentNullException(nameof(requestMessages));
        }

        /// <summary>
        /// Gets the messages that will be sent to the Model/Agent/etc. for this invocation.
        /// </summary>
        public IEnumerable<ChatMessage> RequestMessages { get; }
    }

    /// <summary>
    /// Contains the event conext provided to <see cref="InvokedAsync(InvokedContext, CancellationToken)"/>.
    /// </summary>
    public class InvokedContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokedContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="requestMessages">The messages that were sent to the Model/Agent/etc. for this invocation.</param>
        /// <exception cref="ArgumentNullException">Thrown if <paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokedContext(IEnumerable<ChatMessage> requestMessages)
        {
            RequestMessages = requestMessages ?? throw new ArgumentNullException(nameof(requestMessages));
        }

        /// <summary>
        /// Gets the messages that were sent to the Model/Agent/etc. for this invocation.
        /// </summary>
        public IEnumerable<ChatMessage> RequestMessages { get; }

        /// <summary>
        /// Gets the collection of response messages generated by Model/Agent/etc. if the invocation succeeded.
        /// </summary>
        public IEnumerable<ChatMessage>? ResponseMessages { get; init; }

        /// <summary>
        /// Gets the <see cref="Exception"/> that was thrown during the invocation, if the invocation failed.
        /// </summary>
        public Exception? InvokeException { get; init; }
    }
}
