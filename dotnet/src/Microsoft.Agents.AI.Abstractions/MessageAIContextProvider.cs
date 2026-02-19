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
/// Provides an abstract base class for components that enhance AI context during agent invocations by supplying additional chat messages.
/// </summary>
/// <remarks>
/// <para>
/// A message AI context provider is a component that participates in the agent invocation lifecycle by:
/// <list type="bullet">
/// <item><description>Listening to changes in conversations</description></item>
/// <item><description>Providing additional messages to agents during invocation</description></item>
/// <item><description>Processing invocation results for state management or learning</description></item>
/// </list>
/// </para>
/// <para>
/// Context providers operate through a two-phase lifecycle: they are called at the start of invocation via
/// <see cref="AIContextProvider.InvokingAsync"/> to provide context, and optionally called at the end of invocation via
/// <see cref="AIContextProvider.InvokedAsync"/> to process results.
/// </para>
/// </remarks>
public abstract class MessageAIContextProvider : AIContextProvider
{
    /// <summary>
    /// Initializes a new instance of the <see cref="MessageAIContextProvider"/> class.
    /// </summary>
    /// <param name="provideInputMessageFilter">An optional filter function to apply to input messages before providing messages via <see cref="ProvideMessagesAsync"/>. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to request messages before storing messages via <see cref="AIContextProvider.StoreAIContextAsync"/>. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    protected MessageAIContextProvider(
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
        : base(provideInputMessageFilter, storeInputMessageFilter)
    {
    }

    /// <inheritdoc/>
    protected override async ValueTask<AIContext> ProvideAIContextAsync(AIContextProvider.InvokingContext context, CancellationToken cancellationToken = default)
    {
        // Call ProvideMessagesAsync directly to return only additional messages.
        // The base AIContextProvider.InvokingCoreAsync handles merging with the original input and stamping.
        return new AIContext
        {
            Messages = await this.ProvideMessagesAsync(
                new InvokingContext(context.Agent, context.Session, context.AIContext.Messages ?? []),
                cancellationToken).ConfigureAwait(false)
        };
    }

    /// <summary>
    /// Called at the start of agent invocation to provide additional messages.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="IEnumerable{ChatMessage}"/> to be used by the agent during this invocation.</returns>
    /// <remarks>
    /// <para>
    /// Implementers can load any additional messages required at this time, such as:
    /// <list type="bullet">
    /// <item><description>Retrieving relevant information from knowledge bases</description></item>
    /// <item><description>Adding system instructions or prompts</description></item>
    /// <item><description>Injecting contextual messages from conversation history</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => this.InvokingCoreAsync(Throw.IfNull(context), cancellationToken);

    /// <summary>
    /// Called at the start of agent invocation to provide additional messages.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="IEnumerable{ChatMessage}"/> to be used by the agent during this invocation.</returns>
    /// <remarks>
    /// <para>
    /// Implementers can load any additional messages required at this time, such as:
    /// <list type="bullet">
    /// <item><description>Retrieving relevant information from knowledge bases</description></item>
    /// <item><description>Adding system instructions or prompts</description></item>
    /// <item><description>Injecting contextual messages from conversation history</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The default implementation of this method filters the input messages using the configured provide-input message filter
    /// (which defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages),
    /// then calls <see cref="ProvideMessagesAsync"/> to get additional messages,
    /// stamps any messages with <see cref="AgentRequestMessageSourceType.AIContextProvider"/> source attribution,
    /// and merges the returned messages with the original (unfiltered) input messages.
    /// For most scenarios, overriding <see cref="ProvideMessagesAsync"/> is sufficient to provide additional messages,
    /// while still benefiting from the default filtering, merging and source stamping behavior.
    /// However, for scenarios that require more control over message filtering, merging or source stamping, overriding this method
    /// allows you to directly control the full <see cref="IEnumerable{ChatMessage}"/> returned for the invocation.
    /// </para>
    /// </remarks>
    protected virtual async ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var inputMessages = context.RequestMessages;

        // Create a filtered context for ProvideMessagesAsync, filtering input messages
        // to exclude non-external messages (e.g. chat history, other AI context provider messages).
        var filteredContext = new InvokingContext(
            context.Agent,
            context.Session,
            this.ProvideInputMessageFilter(inputMessages));

        var providedMessages = await this.ProvideMessagesAsync(filteredContext, cancellationToken).ConfigureAwait(false);

        // Stamp and merge provided messages.
        providedMessages = providedMessages.Select(m => m.WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, this.GetType().FullName!));
        return inputMessages.Concat(providedMessages);
    }

    /// <summary>
    /// When overridden in a derived class, provides additional messages to be merged with the input messages for the current invocation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method is called from <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/>.
    /// Note that <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/> can be overridden to directly control messages merging and source stamping, in which case
    /// it is up to the implementer to call this method as needed to retrieve the additional messages.
    /// </para>
    /// <para>
    /// In contrast with <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/>, this method only returns additional messages to be merged with the input,
    /// while <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/> is responsible for returning the full merged <see cref="IEnumerable{ChatMessage}"/> for the invocation.
    /// </para>
    /// </remarks>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains an <see cref="IEnumerable{ChatMessage}"/>
    /// with additional messages to be merged with the input messages.
    /// </returns>
    protected virtual ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        return new ValueTask<IEnumerable<ChatMessage>>([]);
    }

    /// <summary>
    /// Contains the context information provided to <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about the invocation before the underlying AI model is invoked, including the messages
    /// that will be used. Message AI Context providers can use this information to determine what additional messages
    /// should be provided for the invocation.
    /// </remarks>
    public new sealed class InvokingContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokingContext"/> class with the specified request messages.
        /// </summary>
        /// <param name="agent">The agent being invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="requestMessages">The messages to be used by the agent for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="agent"/> or <paramref name="requestMessages"/> is <see langword="null"/>.</exception>
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
        /// Gets the messages that will be used by the agent for this invocation. <see cref="MessageAIContextProvider"/> instances can modify
        /// and return or return a new message list to add additional messages for the invocation.
        /// </summary>
        /// <value>
        /// A collection of <see cref="ChatMessage"/> instances representing the messages that will be used by the agent for this invocation.
        /// </value>
        /// <remarks>
        /// <para>
        /// If multiple <see cref="MessageAIContextProvider"/> instances are used in the same invocation, each <see cref="MessageAIContextProvider"/>
        /// will receive the messages returned by the previous <see cref="MessageAIContextProvider"/> allowing them to build on top of each other's context.
        /// </para>
        /// <para>
        /// The first <see cref="MessageAIContextProvider"/> in the invocation pipeline will receive the
        /// caller provided messages.
        /// </para>
        /// </remarks>
        public IEnumerable<ChatMessage> RequestMessages { get; set { field = Throw.IfNull(value); } }
    }
}
