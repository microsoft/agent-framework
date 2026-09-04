// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Defines the contract for storing and retrieving agent conversation sessions.
/// </summary>
/// <remarks>
/// Implementations enable persistent storage of conversation sessions, allowing conversations to be
/// resumed across HTTP requests, application restarts, or different service instances in hosted scenarios.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSessionStore
{
    /// <summary>
    /// Saves an agent session to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="key">The key that identifies and partitions the session.</param>
    /// <param name="session">The session to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves an agent session from persistent storage, or <see langword="null"/> when no session is stored
    /// for the given identifiers.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="key">The key that identifies and partitions the session.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task whose result contains the restored session, or <see langword="null"/> when nothing is stored for
    /// the given identifiers. This method never creates a session.
    /// </returns>
    /// <remarks>
    /// Each successful lookup must return an independent <see cref="AgentSession"/> instance. Callers may
    /// mutate the returned session and may run concurrent branches from the same identifiers without those
    /// branches observing one another's changes or modifying the stored state. Implementations that cache a
    /// live session must return an independent copy rather than the shared instance.
    /// </remarks>
    public abstract ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves the stored session for the given identifiers, or creates a new one when none is stored.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="key">The key that identifies and partitions the session.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task whose result is always a usable session.</returns>
    /// <remarks>
    /// The default implementation calls <see cref="GetSessionAsync"/> and creates a session through
    /// <see cref="AIAgent.CreateSessionAsync"/> only when the lookup returns <see langword="null"/>.
    /// Implementations that override <see cref="GetSessionAsync"/> receive this behavior automatically.
    /// </remarks>
    public virtual async ValueTask<AgentSession> GetOrCreateSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(agent);

        return await this.GetSessionAsync(agent, key, cancellationToken).ConfigureAwait(false)
            ?? await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
    }
}
