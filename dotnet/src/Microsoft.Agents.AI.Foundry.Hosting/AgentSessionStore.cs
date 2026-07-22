// Copyright (c) Microsoft. All rights reserved.

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
    /// Retrieves a serialized agent session from persistent storage.
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
    /// A task that represents the asynchronous retrieval operation.
    /// The task result contains the session, or a new session if not found.
    /// </returns>
    public abstract ValueTask<AgentSession> GetSessionAsync(
        AIAgent agent,
        string conversationId,
        string? userId,
        CancellationToken cancellationToken = default);
}
