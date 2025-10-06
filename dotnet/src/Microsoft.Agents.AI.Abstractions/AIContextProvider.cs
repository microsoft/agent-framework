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
/// Provides an abstract base class for components that enhance AI context management during agent invocations.
/// </summary>
/// <remarks>
/// <para>
/// An AI context provider is a component that participates in the agent invocation lifecycle by:
/// <list type="bullet">
/// <item><description>Listening to changes in conversations</description></item>
/// <item><description>Providing additional context to AI models or agents before invocation</description></item>
/// <item><description>Supplying additional function tools for enhanced capabilities</description></item>
/// <item><description>Processing invocation results for state management or learning</description></item>
/// </list>
/// </para>
/// <para>
/// Context providers operate through a two-phase lifecycle: they are called before invocation via
/// <see cref="InvokingAsync"/> to provide context, and optionally called after invocation via
/// <see cref="InvokedAsync"/> to process results.
/// </para>
/// </remarks>
public abstract class AIContextProvider
{
    /// <summary>
    /// Called immediately before an AI model or agent is invoked to provide additional context.
    /// </summary>
    /// <param name="context">Contains the request context including the messages that will be sent to the AI model or agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="AIContext"/> with additional context to be provided to the AI model or agent.</returns>
    /// <remarks>
    /// <para>
    /// Implementers can load any additional context required at this time, such as:
    /// <list type="bullet">
    /// <item><description>Retrieving relevant information from knowledge bases</description></item>
    /// <item><description>Adding system instructions or prompts</description></item>
    /// <item><description>Providing function tools for the current invocation</description></item>
    /// <item><description>Injecting contextual messages from conversation history</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The returned context will be combined with context from other providers before being passed to the AI model or agent.
    /// </para>
    /// </remarks>
    public abstract ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Called immediately after an AI model or agent has been invoked to process the results.
    /// </summary>
    /// <param name="context">Contains the invocation context including request messages, response messages, and any exception that occurred.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// <para>
    /// Implementers can use the request and response messages in the provided <paramref name="context"/> to:
    /// <list type="bullet">
    /// <item><description>Update internal state based on conversation outcomes</description></item>
    /// <item><description>Extract and store memories or preferences from user messages</description></item>
    /// <item><description>Log or audit conversation details</description></item>
    /// <item><description>Perform cleanup or finalization tasks</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// This method is called regardless of whether the invocation succeeded or failed.
    /// To check if the invocation was successful, inspect the <see cref="InvokedContext.InvokeException"/> property.
    /// </para>
    /// </remarks>
    public virtual ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
        => default;

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use for the serialization process.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state, or a default <see cref="JsonElement"/> if the provider has no serializable state.</returns>
    /// <remarks>
    /// The default implementation returns a default <see cref="JsonElement"/>. Override this method if the provider
    /// maintains state that should be preserved across sessions or distributed scenarios.
    /// </remarks>
    public virtual JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        => default;

    /// <summary>Asks the <see cref="AIContextProvider"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AIContextProvider"/>,
    /// including itself or any services it might be wrapping. This enables advanced scenarios where consumers need access to
    /// specific provider implementations or their internal services.
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
    /// including itself or any services it might be wrapping. This is a convenience overload of <see cref="GetService(Type, object?)"/>.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

    /// <summary>
    /// Contains the context information provided to <see cref="InvokingAsync(InvokingContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about the upcoming AI model or agent invocation, including the messages
    /// that will be sent. Context providers can use this information to determine what additional context
    /// should be provided for the invocation.
    /// </remarks>
    public class InvokingContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokingContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="requestMessages">The messages to be sent to the AI model or agent for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokingContext(IEnumerable<ChatMessage> requestMessages)
        {
            this.RequestMessages = requestMessages ?? throw new ArgumentNullException(nameof(requestMessages));
        }

        /// <summary>
        /// Gets the messages that will be sent to the AI model or agent for this invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the conversation history
        /// and new messages that will be processed by the AI model or agent.
        /// </value>
        public IEnumerable<ChatMessage> RequestMessages { get; }
    }

    /// <summary>
    /// Contains the context information provided to <see cref="InvokedAsync(InvokedContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about a completed AI model or agent invocation, including both the
    /// request messages that were sent and the response messages that were generated. It also indicates
    /// whether the invocation succeeded or failed.
    /// </remarks>
    public class InvokedContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokedContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="requestMessages">The messages that were sent to the AI model or agent for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokedContext(IEnumerable<ChatMessage> requestMessages)
        {
            this.RequestMessages = requestMessages ?? throw new ArgumentNullException(nameof(requestMessages));
        }

        /// <summary>
        /// Gets the messages that were sent to the AI model or agent for this invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the conversation history
        /// and new messages that were processed by the AI model or agent.
        /// </value>
        public IEnumerable<ChatMessage> RequestMessages { get; }

        /// <summary>
        /// Gets the collection of response messages generated by the AI model or agent if the invocation succeeded.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the response from the AI model or agent,
        /// or <see langword="null"/> if the invocation failed or did not produce response messages.
        /// </value>
        public IEnumerable<ChatMessage>? ResponseMessages { get; init; }

        /// <summary>
        /// Gets the <see cref="Exception"/> that was thrown during the invocation, if the invocation failed.
        /// </summary>
        /// <value>
        /// The exception that caused the invocation to fail, or <see langword="null"/> if the invocation succeeded.
        /// </value>
        public Exception? InvokeException { get; init; }
    }
}
