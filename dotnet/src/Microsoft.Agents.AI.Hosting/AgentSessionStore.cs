// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Defines the contract for storing and retrieving agent conversation threads.
/// </summary>
/// <remarks>
/// <para>
/// Implementations of this interface enable persistent storage of conversation threads,
/// allowing conversations to be resumed across HTTP requests, application restarts,
/// or different service instances in hosted scenarios.
/// </para>
/// <para>
/// <strong>Trust model.</strong> The <c>conversationId</c> passed to
/// <see cref="GetSessionAsync"/> and <see cref="SaveSessionAsync"/> typically originates
/// from the wire (for example, an AG-UI <c>RunAgentInput.ThreadId</c> or an A2A
/// <c>contextId</c>). It is a chain-resume identifier, <em>not</em> an authorization
/// token, and the <c>(agent, conversationId)</c> tuple carries no principal/owner
/// dimension. Hosts that serve more than one user from the same registered store must
/// therefore compose a principal dimension into the lookup key, otherwise any caller
/// who knows or guesses another caller's <c>conversationId</c> can resume
/// that other caller's persisted thread. The framework provides
/// <see cref="IsolationKeyScopedAgentSessionStore"/> as a decorator that rewrites
/// <c>conversationId</c> to include an isolation key resolved from a
/// <see cref="SessionIsolationKeyProvider"/> (for example, the ASP.NET Core
/// <c>ClaimsIdentitySessionIsolationKeyProvider</c> wired up via
/// <c>UseClaimsBasedSessionIsolation(...)</c>). When no provider is registered, the
/// store behaves as a single-namespace persistence layer — appropriate for
/// single-user / first-run / prototyping scenarios but unsafe for multi-user hosts.
/// </para>
/// <para>
/// <strong>Implementer guidance.</strong> Implementations should treat
/// <c>conversationId</c> as opaque: do not parse it, do not impose length
/// or character-set constraints on it, and do not assume it round-trips to the value
/// the caller originally supplied (decorators such as
/// <see cref="IsolationKeyScopedAgentSessionStore"/> may rewrite it before forwarding).
/// Be aware that any logging, telemetry, or audit sink that surfaces
/// <c>conversationId</c> will also surface the isolation prefix when a
/// scoping decorator is in the chain.
/// </para>
/// </remarks>
public abstract class AgentSessionStore
{
    /// <summary>
    /// Saves a serialized agent session to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session.</param>
    /// <param name="session">The session to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveSessionAsync(
        AIAgent agent,
        string conversationId,
        AgentSession session,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent session from persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session to retrieve.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation.
    /// The task result contains the serialized session state, or <see langword="null"/> if not found.
    /// </returns>
    public abstract ValueTask<AgentSession> GetSessionAsync(
        AIAgent agent,
        string conversationId,
        CancellationToken cancellationToken = default);

    /// <summary>Asks the <see cref="AgentSessionStore"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AgentSessionStore"/>,
    /// including itself or any services it might be wrapping. This is particularly useful for inspecting delegation chains
    /// to verify that specific store implementations are present.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AgentSessionStore"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AgentSessionStore"/>,
    /// including itself or any services it might be wrapping. This is particularly useful for inspecting delegation chains
    /// to verify that specific store implementations are present.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;
}
