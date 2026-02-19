// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
/// </list>
/// </para>
/// <para>
/// The <see cref="ChatHistoryProvider"/> is passed a reference to the <see cref="AgentSession"/> via <see cref="InvokingContext"/> and <see cref="InvokedContext"/>
/// allowing it to store state in the <see cref="AgentSession.StateBag"/>. Since a <see cref="ChatHistoryProvider"/> is used with many different sessions, it should
/// not store any session-specific information within its own instance fields. Instead, any session-specific state should be stored in the associated <see cref="AgentSession.StateBag"/>.
/// </para>
/// <para>
/// A <see cref="ChatHistoryProvider"/> is only relevant for scenarios where the underlying AI service that the agent is using
/// does not use in-service chat history storage.
/// </para>
/// </remarks>
public abstract class ChatHistoryProvider
{
    private static IEnumerable<ChatMessage> DefaultExcludeChatHistoryFilter(IEnumerable<ChatMessage> messages)
        => messages.Where(m => m.GetAgentRequestMessageSourceType() != AgentRequestMessageSourceType.ChatHistory);

    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? _provideOutputMessageFilter;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _storeInputMessageFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="provideOutputMessageFilter">An optional filter function to apply to messages when retrieving them from the chat history.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to messages before storing them in the chat history. If not set, defaults to excluding messages with source type <see cref="AgentRequestMessageSourceType.ChatHistory"/>.</param>
    protected ChatHistoryProvider(
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
    {
        this._provideOutputMessageFilter = provideOutputMessageFilter;
        this._storeInputMessageFilter = storeInputMessageFilter ?? DefaultExcludeChatHistoryFilter;
    }

    /// <summary>
    /// Gets the key used to store the provider state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <remarks>
    /// The default value is the name of the concrete type (e.g. <c>"InMemoryChatHistoryProvider"</c>).
    /// Implementations may override this to provide a custom key, for example when multiple
    /// instances of the same provider type are used in the same session.
    /// </remarks>
    public virtual string StateKey => this.GetType().Name;

    /// <summary>
    /// Called at the start of agent invocation to provide messages for the next agent invocation.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains a collection of <see cref="ChatMessage"/>
    /// instances that will be used for the agent invocation.
    /// </returns>
    /// <remarks>
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
    /// </remarks>
    public ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => this.InvokingCoreAsync(Throw.IfNull(context), cancellationToken);

    /// <summary>
    /// Called at the start of agent invocation to provide messages for the next agent invocation.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains a collection of <see cref="ChatMessage"/>
    /// instances that will be used for the agent invocation.
    /// </returns>
    /// <remarks>
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
    /// The default implementation of this method, calls <see cref="ProvideChatHistoryAsync"/> to get the chat history messages, applies the optional retrieval output filter,
    /// and merges the returned messages with the caller provided messages (with chat history messages appearing first) before returning the full message list to be used for the invocation.
    /// For most scenarios, overriding <see cref="ProvideChatHistoryAsync"/> is sufficient to return the desired chat history messages, while still benefiting from the default merging and filtering behavior.
    /// However, for scenarios that require more control over message filtering, merging or source stamping, overriding this method allows you to directly control the full set of messages returned for the invocation.
    /// </para>
    /// </remarks>
    protected virtual async ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var output = await this.ProvideChatHistoryAsync(context, cancellationToken).ConfigureAwait(false);

        if (this._provideOutputMessageFilter is not null)
        {
            output = this._provideOutputMessageFilter(output);
        }

        return output
            .Select(message => message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, this.GetType().FullName!))
            .Concat(context.RequestMessages);
    }

    /// <summary>
    /// When overridden in a derived class, provides the chat history messages to be used for the current invocation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method is called from <see cref="InvokingCoreAsync"/>.
    /// Note that <see cref="InvokingCoreAsync"/> can be overridden to directly control message filtering, merging and source stamping, in which case
    /// it is up to the implementer to call this method as needed to retrieve the unfiltered/unmerged chat history messages.
    /// </para>
    /// <para>
    /// In contrast with <see cref="InvokingCoreAsync"/>, this method only returns additional messages to be added to the request,
    /// while <see cref="InvokingCoreAsync"/> is responsible for returning the full set of messages to be used for the invocation (including caller provided messages).
    /// </para>
    /// <para>
    /// Messages are returned in chronological order to maintain proper conversation flow and context for the agent.
    /// The oldest messages appear first in the collection, followed by more recent messages.
    /// </para>
    /// </remarks>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains a collection of <see cref="ChatMessage"/>
    /// instances in ascending chronological order (oldest first).
    /// </returns>
    protected virtual ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        return new ValueTask<IEnumerable<ChatMessage>>([]);
    }

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
    /// <see cref="InvokingCoreAsync"/> return messages in the correct chronological order.
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
    public ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default) =>
        this.InvokedCoreAsync(Throw.IfNull(context), cancellationToken);

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
    /// <see cref="InvokingCoreAsync"/> return messages in the correct chronological order.
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
    /// <para>
    /// The default implementation of this method, skips execution for any invocation failures, filters messages using the optional storage input message filter
    /// and calls <see cref="StoreChatHistoryAsync"/> to store new chat history messages.
    /// For most scenarios, overriding <see cref="StoreChatHistoryAsync"/> is sufficient to store chat history messages, while still benefiting from the default error handling and filtering behavior.
    /// However, for scenarios that require more control over error handling or message filtering, overriding this method allows you to directly control the messages that are stored for the invocation.
    /// </para>
    /// </remarks>
    protected virtual ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return default;
        }

        var subContext = new InvokedContext(context.Agent, context.Session, this._storeInputMessageFilter(context.RequestMessages), context.ResponseMessages!);
        return this.StoreChatHistoryAsync(subContext, cancellationToken);
    }

    /// <summary>
    /// When overridden in a derived class, adds new messages to the chat history at the end of the agent invocation.
    /// </summary>
    /// <param name="context">Contains the invocation context including request messages, response messages, and any exception that occurred.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous add operation.</returns>
    /// <remarks>
    /// <para>
    /// Messages should be added in the order they were generated to maintain proper chronological sequence.
    /// The <see cref="ChatHistoryProvider"/> is responsible for preserving message ordering and ensuring that subsequent calls to
    /// <see cref="InvokingCoreAsync"/> return messages in the correct chronological order.
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
    /// This method is called from <see cref="InvokedCoreAsync"/>.
    /// Note that <see cref="InvokedCoreAsync"/> can be overridden to directly control message filtering and error handling, in which case
    /// it is up to the implementer to call this method as needed to store messages.
    /// </para>
    /// <para>
    /// In contrast with <see cref="InvokedCoreAsync"/>, this method only stores messages,
    /// while <see cref="InvokedCoreAsync"/> is also responsible for messages filtering and error handling.
    /// </para>
    /// <para>
    /// The default implementation of <see cref="InvokedCoreAsync"/> only calls this method if the invocation succeeded.
    /// </para>
    /// </remarks>
    protected virtual ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default) =>
        default;

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
    /// Contains the context information provided to <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/>.
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
        /// <param name="requestMessages">The messages to be used by the agent for this invocation.</param>
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
        /// Gets the messages that will be used by the agent for this invocation. <see cref="ChatHistoryProvider"/> instances can modify
        /// and return or return a new message list to add additional messages for the invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the messages that will be used by the agent for this invocation.
        /// </value>
        /// <remarks>
        /// <para>
        /// If multiple <see cref="ChatHistoryProvider"/> instances are used in the same invocation, each <see cref="ChatHistoryProvider"/>
        /// will receive the messages returned by the previous <see cref="ChatHistoryProvider"/> allowing them to build on top of each other's context.
        /// </para>
        /// <para>
        /// The first <see cref="ChatHistoryProvider"/> in the invocation pipeline will receive the
        /// caller provided messages.
        /// </para>
        /// </remarks>
        public IEnumerable<ChatMessage> RequestMessages { get; set { field = Throw.IfNull(value); } }
    }

    /// <summary>
    /// Contains the context information provided to <see cref="InvokedCoreAsync(InvokedContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about a completed agent invocation, including the accumulated
    /// request messages (user input, chat history and any others provided by AI context providers) that were used
    /// and the response messages that were generated. It also indicates whether the invocation succeeded or failed.
    /// </remarks>
    public sealed class InvokedContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokedContext"/> class for a successful invocation.
        /// </summary>
        /// <param name="agent">The agent that was invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="requestMessages">The accumulated request messages (user input, chat history and any others provided by AI context providers)
        /// that were used by the agent for this invocation.</param>
        /// <param name="responseMessages">The response messages generated during this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="agent"/>, <paramref name="requestMessages"/>, or <paramref name="responseMessages"/> is <see langword="null"/>.</exception>
        public InvokedContext(
            AIAgent agent,
            AgentSession? session,
            IEnumerable<ChatMessage> requestMessages,
            IEnumerable<ChatMessage> responseMessages)
        {
            this.Agent = Throw.IfNull(agent);
            this.Session = session;
            this.RequestMessages = Throw.IfNull(requestMessages);
            this.ResponseMessages = Throw.IfNull(responseMessages);
        }

        /// <summary>
        /// Initializes a new instance of the <see cref="InvokedContext"/> class for a failed invocation.
        /// </summary>
        /// <param name="agent">The agent that was invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="requestMessages">The accumulated request messages (user input, chat history and any others provided by AI context providers)
        /// that were used by the agent for this invocation.</param>
        /// <param name="invokeException">The exception that caused the invocation to fail.</param>
        /// <exception cref="ArgumentNullException"><paramref name="agent"/>, <paramref name="requestMessages"/>, or <paramref name="invokeException"/> is <see langword="null"/>.</exception>
        public InvokedContext(
            AIAgent agent,
            AgentSession? session,
            IEnumerable<ChatMessage> requestMessages,
            Exception invokeException)
        {
            this.Agent = Throw.IfNull(agent);
            this.Session = session;
            this.RequestMessages = Throw.IfNull(requestMessages);
            this.InvokeException = Throw.IfNull(invokeException);
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
        /// Gets the accumulated request messages (user input, chat history and any others provided by AI context providers)
        /// that were used by the agent for this invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing new messages that were provided by the caller.
        /// This does not include any <see cref="ChatHistoryProvider"/> supplied messages.
        /// </value>
        public IEnumerable<ChatMessage> RequestMessages { get; }

        /// <summary>
        /// Gets the collection of response messages generated during this invocation if the invocation succeeded.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the response,
        /// or <see langword="null"/> if the invocation failed.
        /// </value>
        public IEnumerable<ChatMessage>? ResponseMessages { get; }

        /// <summary>
        /// Gets the <see cref="Exception"/> that was thrown during the invocation, if the invocation failed.
        /// </summary>
        /// <value>
        /// The exception that caused the invocation to fail, or <see langword="null"/> if the invocation succeeded.
        /// </value>
        public Exception? InvokeException { get; }
    }
}
