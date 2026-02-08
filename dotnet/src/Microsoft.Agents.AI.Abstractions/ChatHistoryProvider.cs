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
/// Provides an abstract base class for fetching chat messages from, and adding chat messages to, chat history for the purposes of agent execution.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="ChatHistoryProvider"/> defines the contract that an <see cref="AIAgent"/> can use to retrieve messsages from chat history
/// and provide notification of newly produced messages.
/// Implementations are responsible for managing message persistence, retrieval, and any necessary optimization
/// strategies such as truncation, summarization, or archival.
/// </para>
/// <para>
/// Key responsibilities include:
/// <list type="bullet">
/// <item><description>Storing chat messages with proper ordering and metadata preservation</description></item>
/// <item><description>Retrieving messages in chronological order for agent context</description></item>
/// <item><description>Managing storage limits through truncation, summarization, or other strategies</description></item>
/// <item><description>Supporting serialization for thread persistence and migration</description></item>
/// </list>
/// </para>
/// <para>
/// A <see cref="ChatHistoryProvider"/> is only relevant for scenarios where the underlying AI service that the agent is using
/// does not use in-service chat history storage.
/// </para>
/// </remarks>
public abstract class ChatHistoryProvider
{
    /// <summary>
    /// Called at the start of agent invocation to provide messages from the chat history as context for the next agent invocation.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains a collection of <see cref="ChatMessage"/>
    /// instances in ascending chronological order (oldest first).
    /// </returns>
    /// <remarks>
    /// <para>
    /// Messages are returned in chronological order to maintain proper conversation flow and context for the agent.
    /// The oldest messages appear first in the collection, followed by more recent messages.
    /// </para>
    /// <para>
    /// If the total message history becomes very large, implementations should apply appropriate strategies to manage
    /// storage constraints, such as:
    /// <list type="bullet">
    /// <item><description>Truncating older messages while preserving recent context</description></item>
    /// <item><description>Summarizing message groups to maintain essential context</description></item>
    /// <item><description>Implementing sliding window approaches for message retention</description></item>
    /// <item><description>Archiving old messages while keeping active conversation context</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// Each <see cref="ChatHistoryProvider"/> instance should be associated with a single <see cref="AgentSession"/> to ensure proper message isolation
    /// and context management.
    /// </para>
    /// </remarks>
    public abstract ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Called at the end of the agent invocation to add new messages to the chat history.
    /// </summary>
    /// <param name="context">Contains the invocation context including request messages, response messages, and any exception that occurred.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous add operation.</returns>
    /// <remarks>
    /// <para>
    /// Messages should be added in the order they were generated to maintain proper chronological sequence.
    /// The <see cref="ChatHistoryProvider"/> is responsible for preserving message ordering and ensuring that subsequent calls to
    /// <see cref="InvokingAsync"/> return messages in the correct chronological order.
    /// </para>
    /// <para>
    /// Implementations may perform additional processing during message addition, such as:
    /// <list type="bullet">
    /// <item><description>Validating message content and metadata</description></item>
    /// <item><description>Applying storage optimizations or compression</description></item>
    /// <item><description>Triggering background maintenance operations</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// This method is called regardless of whether the invocation succeeded or failed.
    /// To check if the invocation was successful, inspect the <see cref="InvokedContext.InvokeException"/> property.
    /// </para>
    /// </remarks>
    public abstract ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public abstract JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null);

    /// <summary>Asks the <see cref="ChatHistoryProvider"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="ChatHistoryProvider"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="ChatHistoryProvider"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="ChatHistoryProvider"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

    /// <summary>
    /// Contains the context information provided to <see cref="InvokingAsync(InvokingContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about the invocation including the new messages that will be used.
    /// A <see cref="ChatHistoryProvider"/> can use this information to determine what messages should be provided
    /// for the invocation.
    /// </remarks>
    public sealed class InvokingContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokingContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="agent">The agent being invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="requestMessages">The new messages to be used by the agent for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokingContext(
            AIAgent agent,
            AgentSession? session,
            IEnumerable<ChatMessage> requestMessages)
        {
            this.Agent = Throw.IfNull(agent);
            this.Session = session;
            this.RequestMessages = Throw.IfNull(requestMessages);
        }

        /// <summary>
        /// Gets the agent that is being invoked.
        /// </summary>
        public AIAgent Agent { get; }

        /// <summary>
        /// Gets the agent session associated with the agent invocation.
        /// </summary>
        public AgentSession? Session { get; }

        /// <summary>
        /// Gets the caller provided messages that will be used by the agent for this invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing new messages that were provided by the caller.
        /// </value>
        public IEnumerable<ChatMessage> RequestMessages { get; set { field = Throw.IfNull(value); } }
    }

    /// <summary>
    /// Contains the context information provided to <see cref="InvokedAsync(InvokedContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about a completed agent invocation, including both the
    /// request messages that were used and the response messages that were generated. It also indicates
    /// whether the invocation succeeded or failed.
    /// </remarks>
    public sealed class InvokedContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokedContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="agent">The agent being invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="requestMessages">The caller provided messages that were used by the agent for this invocation.</param>
        /// <param name="chatHistoryProviderMessages">The messages retrieved from the <see cref="ChatHistoryProvider"/> for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="requestMessages"/> is <see langword="null"/>.</exception>
        public InvokedContext(
            AIAgent agent,
            AgentSession? session,
            IEnumerable<ChatMessage> requestMessages,
            IEnumerable<ChatMessage>? chatHistoryProviderMessages)
        {
            this.Agent = Throw.IfNull(agent);
            this.Session = session;
            this.RequestMessages = Throw.IfNull(requestMessages);
            this.ChatHistoryProviderMessages = chatHistoryProviderMessages;
        }

        /// <summary>
        /// Gets the agent that is being invoked.
        /// </summary>
        public AIAgent Agent { get; }

        /// <summary>
        /// Gets the agent session associated with the agent invocation.
        /// </summary>
        public AgentSession? Session { get; }

        /// <summary>
        /// Gets the caller provided messages that were used by the agent for this invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing new messages that were provided by the caller.
        /// This does not include any <see cref="ChatHistoryProvider"/> supplied messages.
        /// </value>
        public IEnumerable<ChatMessage> RequestMessages { get; set { field = Throw.IfNull(value); } }

        /// <summary>
        /// Gets the messages retrieved from the <see cref="ChatHistoryProvider"/> for this invocation, if any.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances that were retrieved from the <see cref="ChatHistoryProvider"/>,
        /// and were used by the agent as part of the invocation.
        /// </value>
        public IEnumerable<ChatMessage>? ChatHistoryProviderMessages { get; set; }

        /// <summary>
        /// Gets or sets the messages provided by the <see cref="AIContextProvider"/> for this invocation, if any.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances that were provided by the <see cref="AIContextProvider"/>,
        /// and were used by the agent as part of the invocation.
        /// </value>
        public IEnumerable<ChatMessage>? AIContextProviderMessages { get; set; }

        /// <summary>
        /// Gets the collection of response messages generated during this invocation if the invocation succeeded.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the response,
        /// or <see langword="null"/> if the invocation failed or did not produce response messages.
        /// </value>
        public IEnumerable<ChatMessage>? ResponseMessages { get; set; }

        /// <summary>
        /// Gets the <see cref="Exception"/> that was thrown during the invocation, if the invocation failed.
        /// </summary>
        /// <value>
        /// The exception that caused the invocation to fail, or <see langword="null"/> if the invocation succeeded.
        /// </value>
        public Exception? InvokeException { get; set; }
    }
}
