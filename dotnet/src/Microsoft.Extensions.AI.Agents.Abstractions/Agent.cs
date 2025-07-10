﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agents. An agent instance may participate in one or more conversations.
/// A conversation may include one or more agents.
/// </summary>
public abstract class Agent
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
    /// Gets the description of the agent (optional).
    /// </summary>
    public virtual string? Description { get; }

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
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public Task<ChatResponse> RunAsync(
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
    public Task<ChatResponse> RunAsync(
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
    public Task<ChatResponse> RunAsync(
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
    public IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
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
    public IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
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
    public IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
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
    /// Checks that the thread is of the expected type, or if null, creates the default thread type.
    /// </summary>
    /// <typeparam name="TThreadType">The expected type of the thead.</typeparam>
    /// <param name="thread">The thread to create if it's null and validate its type if not null.</param>
    /// <param name="constructThread">A callback to use to construct the thread if it's null.</param>
    /// <returns>An async task that completes once all update are complete.</returns>
    protected virtual TThreadType ValidateOrCreateThreadType<TThreadType>(
        AgentThread? thread,
        Func<TThreadType> constructThread)
        where TThreadType : AgentThread
    {
        thread ??= constructThread is not null ? constructThread() : throw new ArgumentNullException(nameof(constructThread));

        if (thread is not TThreadType concreteThreadType)
        {
            throw new NotSupportedException($"{this.GetType().Name} currently only supports agent threads of type {nameof(TThreadType)}.");
        }

        return concreteThreadType;
    }

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
    protected async Task NotifyThreadOfNewMessagesAsync(AgentThread thread, IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(thread);
        _ = Throw.IfNull(messages);

        if (messages.Count > 0)
        {
            await thread.OnNewMessagesAsync(messages, cancellationToken).ConfigureAwait(false);
        }
    }
}
