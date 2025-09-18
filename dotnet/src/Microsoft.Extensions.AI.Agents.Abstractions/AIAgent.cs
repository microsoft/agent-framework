// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agents. An agent instance may participate in one or more conversations.
/// A conversation may include one or more agents.
/// </summary>
public abstract class AIAgent
{
    /// <summary>
    /// Gets the identifier of the agent.
    /// </summary>
    /// <value>
    /// The identifier of the agent. The default is a random GUID value, but for service agents, it will match the id of the agent in the service.
    /// </value>
    public virtual string Id { get; } = Guid.NewGuid().ToString();

    /// <summary>
    /// Gets the name of the agent (optional).
    /// </summary>
    public virtual string? Name { get; }

    /// <summary>
    /// Gets a display name for the agent, which is either the <see cref="Name"/> or <see cref="Id"/> if the name is not set.
    /// </summary>
    public virtual string DisplayName => this.Name ?? this.Id;

    /// <summary>
    /// Gets the description of the agent (optional).
    /// </summary>
    public virtual string? Description { get; }

    /// <summary>Asks the <see cref="AIAgent"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AIAgent"/>,
    /// including itself or any services it might be wrapping. For example, to access the <see cref="AIAgentMetadata"/> for the instance,
    /// <see cref="GetService"/> may be used to request it.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AIAgent"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AIAgent"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

    /// <summary>
    /// Get a new <see cref="AgentThread"/> instance that is compatible with the agent.
    /// </summary>
    /// <returns>A new <see cref="AgentThread"/> instance.</returns>
    /// <remarks>
    /// <para>
    /// If an agent supports multiple thread types, this method should return the default thread
    /// type for the agent or whatever the agent was configured to use.
    /// </para>
    /// <para>
    /// If the thread needs to be created via a service call it would be created on first use.
    /// </para>
    /// </remarks>
    public abstract AgentThread GetNewThread();

    /// <summary>
    /// Deserialize the thread from JSON.
    /// </summary>
    /// <param name="serializedThread">The <see cref="JsonElement"/> representing the thread state.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> to use for deserializing the thread state.</param>
    /// <returns>The deserialized <see cref="AgentThread"/> instance.</returns>
    public abstract AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null);

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="AgentRunResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public Task<AgentRunResponse> RunAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunAsync([], thread, options, cancellationToken);

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="AgentRunResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    /// <remarks>
    /// The provided message string will be treated as a user message.
    /// </remarks>
    public Task<AgentRunResponse> RunAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="AgentRunResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public Task<AgentRunResponse> RunAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="AgentRunResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public abstract Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="AgentRunResponseUpdate"/>.</returns>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync([], thread, options, cancellationToken);

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="AgentRunResponseUpdate"/>.</returns>
    /// <remarks>
    /// The provided message string will be treated as a user message.
    /// </remarks>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunStreamingAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="AgentRunResponseUpdate"/>.</returns>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunStreamingAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="AgentRunResponseUpdate"/>.</returns>
    public abstract IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Notfiy the given thread that new messages are available.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Note that while all agents should notify their threads of new messages,
    /// not all threads will necessarily take action. For some treads, this may be
    /// the only way that they would know that a new message is available to be added
    /// to their history.
    /// </para>
    /// <para>
    /// For other thread types, where history is managed by the service, the thread may
    /// not need to take any action.
    /// </para>
    /// <para>
    /// Where threads manage other memory components that need access to new messages,
    /// notifying the thread will be important, even if the thread itself does not
    /// require the message.
    /// </para>
    /// </remarks>
    /// <param name="thread">The thread to notify of the new messages.</param>
    /// <param name="messages">The messages to pass to the thread.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task that completes once the notification is complete.</returns>
    protected static async Task NotifyThreadOfNewMessagesAsync(AgentThread thread, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(thread);
        _ = Throw.IfNull(messages);

        await thread.MessagesReceivedAsync(messages, cancellationToken).ConfigureAwait(false);
    }
}
