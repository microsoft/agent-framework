// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a hosting wrapper around an <see cref="AIAgent"/> that adds session persistence capabilities
/// for server-hosted scenarios where conversations need to be restored across requests.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AIHostAgent"/> wraps an existing agent implementation and adds the ability to
/// persist and restore conversation threads using an <see cref="AgentSessionStore"/>.
/// </para>
/// <para>
/// This wrapper enables session persistence without requiring type-specific knowledge of the session type,
/// as all session operations work through the base <see cref="AgentSession"/> abstraction.
/// </para>
/// </remarks>
public class AIHostAgent : DelegatingAIAgent
{
    private readonly AgentSessionStore _sessionStore;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIHostAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent implementation to wrap.</param>
    /// <param name="sessionStore">The session store to use for persisting conversation state.</param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerAgent"/> or <paramref name="sessionStore"/> is <see langword="null"/>.
    /// </exception>
    public AIHostAgent(AIAgent innerAgent, AgentSessionStore sessionStore)
        : base(innerAgent)
    {
        this._sessionStore = Throw.IfNull(sessionStore);
    }

    /// <summary>
    /// Gets an existing agent session for the specified conversation, or creates a new one if none exists.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which to retrieve or create the agent session. Cannot be null,
    /// empty, or consist only of white-space characters.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the agent session associated with the
    /// specified conversation. If no session exists, a new session is created and returned.</returns>
    public ValueTask<AgentSession> GetOrCreateSessionAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);

        return this._sessionStore.GetSessionAsync(this.InnerAgent, conversationId, cancellationToken);
    }

    /// <summary>
    /// Persists a conversation session to the session store.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation.</param>
    /// <param name="session">The session to persist.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    /// <exception cref="ArgumentException"><paramref name="conversationId"/> is null or whitespace.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="session"/> is <see langword="null"/>.</exception>
    public ValueTask SaveSessionAsync(string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(conversationId);
        _ = Throw.IfNull(session);

        return this._sessionStore.SaveSessionAsync(this.InnerAgent, conversationId, session, cancellationToken);
    }
}
