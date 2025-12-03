// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a hosting wrapper around an <see cref="AIAgent"/> that adds thread persistence capabilities
/// for server-hosted scenarios where conversations need to be restored across requests.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AIHostAgent"/> wraps an existing agent implementation and adds the ability to
/// persist and restore conversation threads using an <see cref="AgentThreadStore"/>.
/// </para>
/// <para>
/// This wrapper enables thread persistence without requiring type-specific knowledge of the thread type,
/// as all thread operations work through the base <see cref="AgentThread"/> abstraction.
/// </para>
/// </remarks>
public class AIHostAgent : DelegatingAIAgent
{
    private readonly AgentThreadStore _threadStore;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIHostAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent implementation to wrap.</param>
    /// <param name="threadStore">The thread store to use for persisting conversation state.</param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerAgent"/> or <paramref name="threadStore"/> is <see langword="null"/>.
    /// </exception>
    public AIHostAgent(AIAgent innerAgent, AgentThreadStore threadStore)
        : base(innerAgent)
    {
        this._threadStore = Throw.IfNull(threadStore);
    }

    /// <summary>
    /// Gets an existing agent thread for the specified conversation, or creates a new one if none exists.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which to retrieve or create the agent thread. Cannot be null,
    /// empty, or consist only of white-space characters.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the agent thread associated with the
    /// specified conversation. If no thread exists, a new thread is created and returned.</returns>
    public ValueTask<AgentThread> GetOrCreateThreadAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);

        return this._threadStore.GetThreadAsync(this.InnerAgent, conversationId, cancellationToken);
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
    public ValueTask SaveThreadAsync(string conversationId, AgentThread thread, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);
        _ = Throw.IfNull(thread);

        return this._threadStore.SaveThreadAsync(this.InnerAgent, conversationId, thread, cancellationToken);
    }
}
