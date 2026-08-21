// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Defines the contract for storing and retrieving agent conversation sessions.
/// </summary>
/// <remarks>
/// Implementations of this interface enable persistent storage of conversation sessions,
/// allowing conversations to be resumed across HTTP requests, application restarts,
/// or different service instances in hosted scenarios.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSessionStore
{
    /// <summary>
    /// Saves a serialized agent session to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session.</param>
    /// <param name="session">The session to save.</param>
    /// <param name="userId">
    /// The platform-injected per-user partition key (<c>x-agent-user-id</c>) that scopes this session to the
    /// end user who initiated the request. Pass <see langword="null"/> only when there is genuinely no user
    /// context (for example local development without the platform header, or a non-hosted direct caller).
    /// The parameter is required (no default) so every caller consciously decides the scope: implementations
    /// that persist to a shared medium partition by this value so one user can never observe another user's
    /// sessions, and an accidental unscoped save cannot happen silently.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveSessionAsync(
        AIAgent agent,
        string conversationId,
        AgentSession session,
        string? userId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent session from persistent storage, or <see langword="null"/> when
    /// no session is stored for the given identifiers.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session to retrieve.</param>
    /// <param name="userId">
    /// The platform-injected per-user partition key (<c>x-agent-user-id</c>) that scopes this session to the
    /// end user who initiated the request. Pass <see langword="null"/> only when there is genuinely no user
    /// context (for example local development without the platform header, or a non-hosted direct caller).
    /// The parameter is required (no default); it must match the value used when the session was saved,
    /// otherwise a different (or new) session is returned.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation. The task result contains the restored
    /// session, or <see langword="null"/> when nothing is stored for the given identifiers. This is a plain
    /// lookup: it never creates a session. Use <see cref="GetOrCreateSessionAsync"/> to get a ready-to-use
    /// session (loading an existing one or creating a new one), and use this method when the caller needs to
    /// distinguish a resumed session from a fresh one (a non-null result means a prior turn established it).
    /// </returns>
    public abstract ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        string conversationId,
        string? userId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves the stored session for the given identifiers, or creates a new one via
    /// <see cref="AIAgent.CreateSessionAsync"/> when none is stored.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session to retrieve.</param>
    /// <param name="userId">The per-user partition key; see <see cref="GetSessionAsync"/> for its meaning.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task whose result is always a usable session, never <see langword="null"/>.</returns>
    /// <remarks>
    /// This is the convenience path for callers that only need a session to work with and do not care whether
    /// it was loaded or freshly created. It is implemented in terms of <see cref="GetSessionAsync"/>, so a
    /// store overriding that method gets this behavior for free.
    /// </remarks>
    public virtual async ValueTask<AgentSession> GetOrCreateSessionAsync(
        AIAgent agent,
        string conversationId,
        string? userId,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);

        return await this.GetSessionAsync(agent, conversationId, userId, cancellationToken).ConfigureAwait(false)
            ?? await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
    }
}
