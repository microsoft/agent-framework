// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a hosting wrapper around an <see cref="AIAgent"/> that adds thread persistence capabilities
/// for server-hosted scenarios where conversations need to be restored across requests.
/// </summary>
/// <typeparam name="TThread">The type of <see cref="AgentThread"/> used by the wrapped agent.</typeparam>
/// <remarks>
/// <para>
/// <see cref="AIHostAgent{TThread}"/> wraps an existing agent implementation and adds the ability to
/// persist and restore conversation threads using an <see cref="IAgentThreadStore"/>.
/// </para>
/// <para>
/// The generic type parameter ensures type safety when working with threads, eliminating runtime
/// type checks and enabling better IDE support.
/// </para>
/// </remarks>
public class AIHostAgent<TThread> : AIAgent
    where TThread : AgentThread
{
    private readonly AIAgent _innerAgent;
    private readonly IAgentThreadStore _threadStore;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIHostAgent{TThread}"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent implementation to wrap.</param>
    /// <param name="threadStore">The thread store to use for persisting conversation state.</param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerAgent"/> or <paramref name="threadStore"/> is <see langword="null"/>.
    /// </exception>
    public AIHostAgent(AIAgent innerAgent, IAgentThreadStore threadStore)
    {
        this._innerAgent = Throw.IfNull(innerAgent);
        this._threadStore = Throw.IfNull(threadStore);
    }

    /// <inheritdoc/>
    public override string Id => this._innerAgent.Id;

    /// <inheritdoc/>
    public override string? Name => this._innerAgent.Name;

    /// <inheritdoc/>
    public override string? Description => this._innerAgent.Description;

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
        => base.GetService(serviceType, serviceKey) ?? this._innerAgent.GetService(serviceType, serviceKey);

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => this._innerAgent.GetNewThread();

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => this._innerAgent.DeserializeThread(serializedThread, jsonSerializerOptions);

    /// <summary>
    /// Restores a conversation thread from the thread store using the specified conversation ID.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation to restore.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains the restored thread,
    /// or <see langword="null"/> if no thread with the given ID exists in the store.
    /// </returns>
    /// <exception cref="ArgumentException"><paramref name="conversationId"/> is null or whitespace.</exception>
    public async ValueTask<TThread?> RestoreThreadAsync(
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);

        var serializedThread = await this._threadStore.GetOrCreateThreadAsync(
            conversationId,
            this.Id,
            cancellationToken).ConfigureAwait(false);

        if (serializedThread is null)
        {
            return null;
        }

        var thread = this._innerAgent.DeserializeThread(serializedThread.Value);
        return thread as TThread;
    }

    /// <summary>
    /// Persists a conversation thread to the thread store.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation.</param>
    /// <param name="thread">The thread to persist.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    /// <exception cref="ArgumentException"><paramref name="conversationId"/> is null or whitespace.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="thread"/> is <see langword="null"/>.</exception>
    public async ValueTask SaveThreadAsync(
        string conversationId,
        TThread thread,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);
        _ = Throw.IfNull(thread);

        var serializedThread = thread.Serialize();
        await this._threadStore.SaveThreadAsync(
            conversationId,
            this.Id,
            serializedThread,
            cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this._innerAgent.RunAsync(messages, thread, options, cancellationToken);

    /// <inheritdoc/>
    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this._innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
}
