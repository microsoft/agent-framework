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
/// Provides an abstract base class for components that enhance AI context during agent invocations.
/// </summary>
/// <remarks>
/// <para>
/// An AI context provider is a component that participates in the agent invocation lifecycle by:
/// <list type="bullet">
/// <item><description>Listening to changes in conversations</description></item>
/// <item><description>Providing additional context to agents during invocation</description></item>
/// <item><description>Supplying additional function tools for enhanced capabilities</description></item>
/// <item><description>Processing invocation results for state management or learning</description></item>
/// </list>
/// </para>
/// <para>
/// Context providers operate through a two-phase lifecycle: they are called at the start of invocation via
/// <see cref="InvokingAsync"/> to provide context, and optionally called at the end of invocation via
/// <see cref="InvokedAsync"/> to process results.
/// </para>
/// </remarks>
public abstract class AIContextProvider
{
    private static IEnumerable<ChatMessage> DefaultExternalOnlyFilter(IEnumerable<ChatMessage> messages)
        => messages.Where(m => m.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.External);

    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _provideInputMessageFilter;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _storeInputMessageFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIContextProvider"/> class.
    /// </summary>
    /// <param name="provideInputMessageFilter">An optional filter function to apply to input messages before providing context via <see cref="ProvideAIContextAsync"/>. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to request messages before storing context via <see cref="StoreAIContextAsync"/>. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    protected AIContextProvider(
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
    {
        this._provideInputMessageFilter = provideInputMessageFilter ?? DefaultExternalOnlyFilter;
        this._storeInputMessageFilter = storeInputMessageFilter ?? DefaultExternalOnlyFilter;
    }

    /// <summary>
    /// Gets the key used to store the provider state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <remarks>
    /// The default value is the name of the concrete type (e.g. <c>"TextSearchProvider"</c>).
    /// Implementations may override this to provide a custom key, for example when multiple
    /// instances of the same provider type are used in the same session.
    /// </remarks>
    public virtual string StateKey => this.GetType().Name;

    /// <summary>
    /// Called at the start of agent invocation to provide additional context.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="AIContext"/> with additional context to be used by the agent during this invocation.</returns>
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
    /// </remarks>
    public ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => this.InvokingCoreAsync(Throw.IfNull(context), cancellationToken);

    /// <summary>
    /// Called at the start of agent invocation to provide additional context.
    /// </summary>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="AIContext"/> with additional context to be used by the agent during this invocation.</returns>
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
    /// The default implementation of this method filters the input messages using the configured provide-input message filter
    /// (which defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages),
    /// then calls <see cref="ProvideAIContextAsync"/> to get additional context,
    /// stamps any messages from the returned context with <see cref="AgentRequestMessageSourceType.AIContextProvider"/> source attribution,
    /// and merges the returned context with the original (unfiltered) input context (concatenating instructions, messages, and tools).
    /// For most scenarios, overriding <see cref="ProvideAIContextAsync"/> is sufficient to provide additional context,
    /// while still benefiting from the default filtering, merging and source stamping behavior.
    /// However, for scenarios that require more control over context filtering, merging or source stamping, overriding this method
    /// allows you to directly control the full <see cref="AIContext"/> returned for the invocation.
    /// </para>
    /// </remarks>
    protected virtual async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var inputContext = context.AIContext;

        // Create a filtered context for ProvideAIContextAsync, filtering input messages
        // to exclude non-external messages (e.g. chat history, other AI context provider messages).
        var filteredContext = new InvokingContext(
            context.Agent,
            context.Session,
            new AIContext
            {
                Instructions = inputContext.Instructions,
                Messages = inputContext.Messages is not null ? this._provideInputMessageFilter(inputContext.Messages) : null,
                Tools = inputContext.Tools
            });

        var provided = await this.ProvideAIContextAsync(filteredContext, cancellationToken).ConfigureAwait(false);

        var mergedInstructions = (inputContext.Instructions, provided.Instructions) switch
        {
            (null, null) => null,
            (string a, null) => a,
            (null, string b) => b,
            (string a, string b) => a + "\n" + b
        };

        var providedMessages = provided.Messages is not null
            ? provided.Messages.Select(m => m.WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, this.GetType().FullName!))
            : null;

        var mergedMessages = (inputContext.Messages, providedMessages) switch
        {
            (null, null) => null,
            (var a, null) => a,
            (null, var b) => b,
            (var a, var b) => a.Concat(b)
        };

        var mergedTools = (inputContext.Tools, provided.Tools) switch
        {
            (null, null) => null,
            (var a, null) => a,
            (null, var b) => b,
            (var a, var b) => a.Concat(b)
        };

        return new AIContext
        {
            Instructions = mergedInstructions,
            Messages = mergedMessages,
            Tools = mergedTools
        };
    }

    /// <summary>
    /// When overridden in a derived class, provides additional AI context to be merged with the input context for the current invocation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method is called from <see cref="InvokingCoreAsync"/>.
    /// Note that <see cref="InvokingCoreAsync"/> can be overridden to directly control context merging and source stamping, in which case
    /// it is up to the implementer to call this method as needed to retrieve the additional context.
    /// </para>
    /// <para>
    /// In contrast with <see cref="InvokingCoreAsync"/>, this method only returns additional context to be merged with the input,
    /// while <see cref="InvokingCoreAsync"/> is responsible for returning the full merged <see cref="AIContext"/> for the invocation.
    /// </para>
    /// </remarks>
    /// <param name="context">Contains the request context including the caller provided messages that will be used by the agent for this invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains an <see cref="AIContext"/>
    /// with additional context to be merged with the input context.
    /// </returns>
    protected virtual ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        return new ValueTask<AIContext>(new AIContext());
    }

    /// <summary>
    /// Called at the end of the agent invocation to process the invocation results.
    /// </summary>
    /// <param name="context">Contains the invocation context including request messages, response messages, and any exception that occurred.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// <para>
    /// Implementers can use the request and response messages in the provided <paramref name="context"/> to:
    /// <list type="bullet">
    /// <item><description>Update state based on conversation outcomes</description></item>
    /// <item><description>Extract and store memories or preferences from user messages</description></item>
    /// <item><description>Log or audit conversation details</description></item>
    /// <item><description>Perform cleanup or finalization tasks</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The <see cref="AIContextProvider"/> is passed a reference to the <see cref="AgentSession"/> via <see cref="InvokingContext"/> and <see cref="InvokedContext"/>
    /// allowing it to store state in the <see cref="AgentSession.StateBag"/>. Since an <see cref="AIContextProvider"/> is used with many different sessions, it should
    /// not store any session-specific information within its own instance fields. Instead, any session-specific state should be stored in the associated <see cref="AgentSession.StateBag"/>.
    /// </para>
    /// <para>
    /// This method is called regardless of whether the invocation succeeded or failed.
    /// To check if the invocation was successful, inspect the <see cref="InvokedContext.InvokeException"/> property.
    /// </para>
    /// </remarks>
    public ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
        => this.InvokedCoreAsync(Throw.IfNull(context), cancellationToken);

    /// <summary>
    /// Called at the end of the agent invocation to process the invocation results.
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
    /// <para>
    /// The default implementation of this method skips execution for any invocation failures,
    /// filters the request messages using the configured store-input message filter
    /// (which defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages),
    /// and calls <see cref="StoreAIContextAsync"/> to process the invocation results.
    /// For most scenarios, overriding <see cref="StoreAIContextAsync"/> is sufficient to process invocation results,
    /// while still benefiting from the default error handling and filtering behavior.
    /// However, for scenarios that require more control over error handling or message filtering, overriding this method
    /// allows you to directly control the processing of invocation results.
    /// </para>
    /// </remarks>
    protected virtual ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return default;
        }

        var subContext = new InvokedContext(context.Agent, context.Session, this._storeInputMessageFilter(context.RequestMessages), context.ResponseMessages!);
        return this.StoreAIContextAsync(subContext, cancellationToken);
    }

    /// <summary>
    /// When overridden in a derived class, processes invocation results at the end of the agent invocation.
    /// </summary>
    /// <param name="context">Contains the invocation context including request messages, response messages, and any exception that occurred.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// <para>
    /// This method is called from <see cref="InvokedCoreAsync"/>.
    /// Note that <see cref="InvokedCoreAsync"/> can be overridden to directly control error handling, in which case
    /// it is up to the implementer to call this method as needed to process the invocation results.
    /// </para>
    /// <para>
    /// In contrast with <see cref="InvokedCoreAsync"/>, this method only processes the invocation results,
    /// while <see cref="InvokedCoreAsync"/> is also responsible for error handling.
    /// </para>
    /// <para>
    /// The default implementation of <see cref="InvokedCoreAsync"/> only calls this method if the invocation succeeded.
    /// </para>
    /// </remarks>
    protected virtual ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default) =>
        default;

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
    /// Contains the context information provided to <see cref="InvokingCoreAsync(InvokingContext, CancellationToken)"/>.
    /// </summary>
    /// <remarks>
    /// This class provides context about the invocation before the underlying AI model is invoked, including the messages
    /// that will be used. Context providers can use this information to determine what additional context
    /// should be provided for the invocation.
    /// </remarks>
    public sealed class InvokingContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="InvokingContext"/> class.
        /// </summary>
        /// <param name="agent">The agent being invoked.</param>
        /// <param name="session">The session associated with the agent invocation.</param>
        /// <param name="aiContext">The AI context to be used by the agent for this invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="agent"/> or <paramref name="aiContext"/> is <see langword="null"/>.</exception>
        public InvokingContext(
            AIAgent agent,
            AgentSession? session,
            AIContext aiContext)
        {
            this.Agent = Throw.IfNull(agent);
            this.Session = session;
            this.AIContext = Throw.IfNull(aiContext);
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
        /// Gets the <see cref="AIContext"/> being built for the current invocation. Context providers can modify
        /// and return or return a new <see cref="AIContext"/> instance to provide additional context for the invocation.
        /// </summary>
        /// <remarks>
        /// <para>
        /// If multiple <see cref="AIContextProvider"/> instances are used in the same invocation, each <see cref="AIContextProvider"/>
        /// will receive the context returned by the previous <see cref="AIContextProvider"/> allowing them to build on top of each other's context.
        /// </para>
        /// <para>
        /// The first <see cref="AIContextProvider"/> in the invocation pipeline will receive an <see cref="AIContext"/> instance
        /// that already contains the caller provided messages that will be used by the agent for this invocation.
        /// </para>
        /// <para>
        /// It may also contain messages from chat history, if a <see cref="ChatHistoryProvider"/> is being used.
        /// </para>
        /// </remarks>
        public AIContext AIContext { get; }
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
        /// A collection of <see cref="ChatMessage"/> instances representing all messages that were used by the agent for this invocation.
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
