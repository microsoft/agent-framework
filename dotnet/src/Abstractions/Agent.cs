// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents;

/// <summary>
/// Base abstraction for all agents.
/// </summary>
public abstract class Agent
{
    /// <summary>
    /// Gets the description of the agent (optional).
    /// </summary>
    public string? Description { get; init; }

    /// <summary>
    /// Gets the identifier of the agent (optional).
    /// </summary>
    /// <value>
    /// The identifier of the agent. The default is a random GUID value, but that can be overridden.
    /// </value>
    public string Id { get; init; } = Guid.NewGuid().ToString();

    /// <summary>
    /// Gets the name of the agent (optional).
    /// </summary>
    public string? Name { get; init; }

    /// <summary>
    /// A <see cref="ILoggerFactory"/> for this <see cref="Agent"/>.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; init; }

    /// <summary>
    /// Gets the instructions for the agent (optional).
    /// </summary>
    public string? Instructions { get; init; }

    /// <summary>
    /// Gets or sets the functions that the agent can call (optional).
    /// </summary>
    public IEnumerable<AIFunction>? Functions { get; init; }

    /// <summary>
    /// Invoke the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.InvokeAsync((ICollection<ChatMessage>)[], thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// <para>
    /// The provided message string will be treated as a user message.
    /// </para>
    /// <para>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </para>
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        string message,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Verify.NotNull(message);

        return this.InvokeAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Verify.NotNull(message);

        return this.InvokeAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public abstract IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Invoke the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.InvokeStreamingAsync((ICollection<ChatMessage>)[], thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// <para>
    /// The provided message string will be treated as a user message.
    /// </para>
    /// <para>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </para>
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        string message,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Verify.NotNull(message);

        return this.InvokeStreamingAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public virtual IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Verify.NotNull(message);

        return this.InvokeStreamingAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatResponseUpdate"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public abstract IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// The <see cref="ILogger"/> associated with this  <see cref="Agent"/>.
    /// </summary>
    protected ILogger Logger => this._logger ??= this.ActiveLoggerFactory.CreateLogger(this.GetType());

    /// <summary>
    /// Get the active logger factory, if defined; otherwise, provide the default.
    /// </summary>
    protected virtual ILoggerFactory ActiveLoggerFactory => this.LoggerFactory ?? NullLoggerFactory.Instance;

    private ILogger? _logger;

    /// <summary>
    /// Ensures that the thread exists, is of the expected type, and is active, plus adds the provided message to the thread.
    /// </summary>
    /// <typeparam name="TThreadType">The expected type of the thead.</typeparam>
    /// <param name="messages">The messages to add to the thread once it is setup.</param>
    /// <param name="thread">The thread to create if it's null, validate it's type if not null, and start if it is not active.</param>
    /// <param name="constructThread">A callback to use to construct the thread if it's null.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async task that completes once all update are complete.</returns>
    /// <exception cref="InvalidOperationException"></exception>
    protected virtual async Task<TThreadType> EnsureThreadExistsWithMessagesAsync<TThreadType>(
        ICollection<ChatMessage> messages,
        AgentThread? thread,
        Func<TThreadType> constructThread,
        CancellationToken cancellationToken)
        where TThreadType : AgentThread
    {
        if (thread is null)
        {
            thread = constructThread();
        }

        if (thread is not TThreadType concreteThreadType)
        {
            throw new InvalidOperationException($"{this.GetType().Name} currently only supports agent threads of type {nameof(TThreadType)}.");
        }

        // We have to explicitly call create here to ensure that the thread is created
        // before we invoke using the thread. While threads will be created when
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
#pragma warning disable VSTHRD200 // Use "Async" suffix for async methods
    protected Task NotifyThreadOfNewMessage(AgentThread thread, ChatMessage message, CancellationToken cancellationToken)
#pragma warning restore VSTHRD200 // Use "Async" suffix for async methods
    {
        return thread.OnNewMessageAsync(message, cancellationToken);
    }
}
