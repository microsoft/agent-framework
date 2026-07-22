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
/// <strong>Trust model.</strong> The <c>sessionStoreId</c> passed to
/// <see cref="GetSessionAsync"/> and <see cref="SaveSessionAsync"/> is the id under which the session is
/// stored. It typically originates from the wire (for example, an AG-UI <c>RunAgentInput.ThreadId</c> or an
/// A2A <c>contextId</c>). It is a chain-resume identifier, <em>not</em> an authorization
/// token, and the <c>(agent, sessionStoreId)</c> tuple carries no principal/owner
/// dimension. Hosts that serve more than one user from the same registered store must
/// therefore compose a principal dimension into the lookup key, otherwise any caller
/// who knows or guesses another caller's <c>sessionStoreId</c> can resume
/// that other caller's persisted thread. The framework provides
/// <see cref="IsolationKeyScopedAgentSessionStore"/> as a decorator that rewrites
/// <c>sessionStoreId</c> to include an isolation key resolved from a
/// <see cref="SessionIsolationKeyProvider"/> (for example, the ASP.NET Core
/// <c>ClaimsIdentitySessionIsolationKeyProvider</c> wired up via
/// <c>UseClaimsBasedSessionIsolation(...)</c>). When no provider is registered, the
/// store behaves as a single-namespace persistence layer — appropriate for
/// single-user / first-run / prototyping scenarios but unsafe for multi-user hosts.
/// </para>
/// <para>
/// <strong>Implementer guidance.</strong> Implementations should treat
/// <c>sessionStoreId</c> as opaque: do not parse it, do not impose length
/// or character-set constraints on it, and do not assume it round-trips to the value
/// the caller originally supplied (decorators such as
/// <see cref="IsolationKeyScopedAgentSessionStore"/> may rewrite it before forwarding).
/// Be aware that any logging, telemetry, or audit sink that surfaces
/// <c>sessionStoreId</c> will also surface the isolation prefix when a
/// scoping decorator is in the chain.
/// </para>
/// </remarks>
public abstract class AgentSessionStore
{
    /// <summary>
    /// Saves a serialized agent session to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="sessionStoreId">The id under which the session is stored.</param>
    /// <param name="session">The session to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveSessionAsync(
        AIAgent agent,
        string sessionStoreId,
        AgentSession session,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent session from persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="sessionStoreId">The id under which the session is stored.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation. The task result contains the
    /// restored <see cref="AgentSession"/>, or a newly created session when nothing is stored for the id.
    /// </returns>
    /// <remarks>
    /// <strong>Isolation.</strong> Each call must return an <em>independent</em> <see cref="AgentSession"/>
    /// instance. Callers may mutate the returned session, and may run several concurrent branches from the
    /// same <paramref name="sessionStoreId"/> (for example forking from an OpenAI Responses
    /// <c>previous_response_id</c>), without those branches observing one another's mutations or altering the
    /// stored state. The in-box stores satisfy this by returning a fresh instance rehydrated from a serialized
    /// snapshot on every call; implementations that cache a live <see cref="AgentSession"/> must return an
    /// independent copy (for example by round-tripping through
    /// <see cref="AIAgent.SerializeSessionAsync(AgentSession, System.Text.Json.JsonSerializerOptions?, CancellationToken)"/>
    /// and <see cref="AIAgent.DeserializeSessionAsync(System.Text.Json.JsonElement, System.Text.Json.JsonSerializerOptions?, CancellationToken)"/>)
    /// rather than handing back the shared instance.
    /// </remarks>
    public abstract ValueTask<AgentSession> GetSessionAsync(
        AIAgent agent,
        string sessionStoreId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a stored agent session, if present.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="sessionStoreId">The id under which the session is stored.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous delete operation.</returns>
    /// <remarks>
    /// Implementations that support removal delete the session and treat a missing session as a no-op.
    /// Implementations that genuinely cannot support deletion should throw <see cref="NotSupportedException"/>.
    /// </remarks>
    /// <exception cref="NotSupportedException">The store does not support deletion.</exception>
    public abstract ValueTask DeleteSessionAsync(
        AIAgent agent,
        string sessionStoreId,
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
