// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Base abstraction for all agents. An agent instance may participate in one or more conversations.
/// A conversation may include one or more agents.
/// </summary>
public abstract class Agent
{
    /// <summary>
    /// Gets the identifier of the agent (optional).
    /// </summary>
    /// <value>
    /// The identifier of the agent. The default is a random GUID value, but for service agents, it will match the id of the agent in the service.
    /// </value>
    public virtual string Id => Guid.NewGuid().ToString();

    /// <summary>
    /// Gets the name of the agent (optional).
    /// </summary>
    public virtual string? Name { get; }

    /// <summary>
    /// Gets the description of the agent (optional).
    /// </summary>
    public virtual string? Description { get; }

    /// <summary>
    /// Gets the instructions for the agent (optional).
    /// </summary>
    public virtual string? Instructions { get; }

    /// <summary>
    /// Create a new <see cref="AgentThread"/> that is compatible with the agent.
    /// </summary>
    /// <returns>A new <see cref="AgentThread"/> instance that is in the created state.</returns>
    /// <remarks>
    /// If an agent supports multiple thread types, this method should return the default thread
    /// type for the agent or whatever the agent was configured to use.
    /// </remarks>
    public abstract Task<AgentThread> CreateThreadAsync();

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public virtual Task<ChatResponse> RunAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.RunAsync((IReadOnlyCollection<ChatMessage>)[], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    /// <remarks>
    /// The provided message string will be treated as a user message.
    /// </remarks>
    public virtual Task<ChatResponse> RunAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(message);

        return this.RunAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public virtual Task<ChatResponse> RunAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(message);

        return this.RunAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public abstract Task<ChatResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/>.</returns>
    public virtual IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.RunStreamingAsync((IReadOnlyCollection<ChatMessage>)[], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/>.</returns>
    /// <remarks>
    /// The provided message string will be treated as a user message.
    /// </remarks>
    public virtual IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(message);

        return this.RunStreamingAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/>.</returns>
    public virtual IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(message);

        return this.RunStreamingAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/>.</returns>
    public abstract IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Ensures that the thread exists, is of the expected type, and is active, plus adds the provided message to the thread.
    /// </summary>
    /// <typeparam name="TThreadType">The expected type of the thead.</typeparam>
    /// <param name="messages">The messages to add to the thread once it is setup.</param>
    /// <param name="thread">The thread to create if it's null, validate it's type if not null, and start if it is not active.</param>
    /// <param name="constructThread">A callback to use to construct the thread if it's null.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task that completes once all update are complete.</returns>
    protected virtual async Task<TThreadType> EnsureThreadExistsWithMessagesAsync<TThreadType>(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread,
        Func<TThreadType> constructThread,
        CancellationToken cancellationToken)
        where TThreadType : AgentThread
    {
        Throw.IfNull(messages);

        thread ??= constructThread is not null ? constructThread() : throw new ArgumentNullException(nameof(constructThread));

        if (thread is not TThreadType concreteThreadType)
        {
            throw new NotSupportedException($"{this.GetType().Name} currently only supports agent threads of type {nameof(TThreadType)}.");
        }

        // We have to explicitly call create here to ensure that the thread is created
        // before we run using the thread. While threads will be created when
        // notified of new messages, some agents support invoking without a message,
        // and in that case no messages will be sent in the next step.
        await thread.CreateAsync(cancellationToken).ConfigureAwait(false);

        // Notify the thread that new messages are available.
        foreach (var message in messages)
        {
            await this.NotifyThreadOfNewMessage(thread, message, cancellationToken).ConfigureAwait(false);
        }

        return concreteThreadType;
    }

    /// <summary>
    /// Notfiy the given thread that a new message is available.
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
    /// <param name="thread">The thread to notify of the new message.</param>
    /// <param name="message">The message to pass to the thread.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task that completes once the notification is complete.</returns>
    protected Task NotifyThreadOfNewMessage(AgentThread thread, ChatMessage message, CancellationToken cancellationToken)
    {
        return thread.OnNewMessageAsync(message, cancellationToken);
    }
}
