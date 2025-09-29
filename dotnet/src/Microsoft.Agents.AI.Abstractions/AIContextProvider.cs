// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

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
        => default;

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        => default;

    /// <summary>Asks the <see cref="AIContextProvider"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AIContextProvider"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AIContextProvider"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AIContextProvider"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

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
