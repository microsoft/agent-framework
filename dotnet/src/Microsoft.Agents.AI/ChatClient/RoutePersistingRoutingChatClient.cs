// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="RoutingChatClient"/> that routes each request to one of several named inner chat clients, based
/// on a route that is persisted in the agent session's <see cref="AgentSessionStateBag"/>.
/// </summary>
/// <remarks>
/// <para>
/// This client holds multiple named inner clients (routes) and selects one per request. The route that is active
/// for a session is stored in the session's <see cref="AgentSessionStateBag"/> as an
/// <see cref="AgentSessionRoutingState"/>, so the selection survives for the lifetime of the session and across
/// session serialization. Use <see cref="SetActiveRoute"/> and <see cref="GetActiveRoute"/> to change or inspect
/// the active route for a session.
/// </para>
/// <para>
/// Because the conversation history is carried by the agent's session rather than by the routed client, switching
/// route mid-conversation preserves the full history for whichever client handles the next turn.
/// </para>
/// <para>
/// All route clients must use client-side conversation history. Service-stored history is isolated to its
/// originating service and cannot be shared when another route handles the next request.
/// </para>
/// <para>
/// A new session starts on <see cref="RoutePersistingRoutingChatClientOptions.DefaultRoute"/>, or on the first entry of
/// the routes dictionary when no default is configured.
/// </para>
/// <para>
/// This client resolves the current session from <see cref="AIAgent.CurrentRunContext"/>, which is set
/// automatically when an agent's run methods are called. It must therefore be invoked within an agent run that
/// has a resolved session; invoking it outside of an agent run, or before a session is resolved, throws an
/// <see cref="InvalidOperationException"/>.
/// </para>
/// <para>
/// Service discovery is best-effort and route-specific: <see cref="GetService"/> forwards to the active route during
/// a run and to the default route otherwise. When routing among undecorated chat clients, middleware that must apply
/// consistently to every route, such as <see cref="FunctionInvokingChatClient"/>, should wrap this routing client
/// rather than individual route clients. Applications that register heterogeneous, pre-decorated route clients are
/// responsible for ensuring their middleware stacks are compatible.
/// </para>
/// <para>
/// For routing policies that are not persisted per session, such as content-based or failover routing, use the
/// routing clients provided by <c>Microsoft.Extensions.AI</c> directly.
/// </para>
/// <para>
/// Instances are thread-safe across different sessions as long as <see cref="Routes"/> is not modified. Route
/// mutations must only be performed when no requests are in flight. A single session must not be used concurrently,
/// since the per-session routing state assumes only one request per session is in flight at a time.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class RoutePersistingRoutingChatClient : RoutingChatClient
{
    private readonly ProviderSessionState<AgentSessionRoutingState> _sessionState;
    private readonly string? _defaultRoute;
    private readonly bool _ownsInnerClients;
    private int _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="RoutePersistingRoutingChatClient"/> class.
    /// </summary>
    /// <param name="routes">
    /// The initial inner clients to route to, keyed by route name. The entries are copied into <see cref="Routes"/>
    /// and may be modified there after construction.
    /// </param>
    /// <param name="options">Optional settings that control routing behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="routes"/> is <see langword="null"/>.</exception>
    public RoutePersistingRoutingChatClient(
        IReadOnlyDictionary<string, IChatClient> routes,
        RoutePersistingRoutingChatClientOptions? options = null)
    {
        _ = Throw.IfNull(routes);

        var mutableRoutes = new Dictionary<string, IChatClient>();
        foreach (var route in routes)
        {
            mutableRoutes.Add(route.Key, route.Value);
        }

        this.Routes = mutableRoutes;
        this._defaultRoute = options?.DefaultRoute ?? mutableRoutes.Keys.FirstOrDefault();
        this._ownsInnerClients = options?.OwnsInnerClients ?? false;
        this._sessionState = new ProviderSessionState<AgentSessionRoutingState>(
            _ => new AgentSessionRoutingState { ActiveRoute = this._defaultRoute },
            options?.StateKey ?? nameof(RoutePersistingRoutingChatClient),
            AgentJsonUtilities.DefaultOptions);
    }

    /// <summary>
    /// Gets the mutable routes that requests can be routed to, keyed by route name.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The dictionary is owned by this instance and initially contains a copy of the entries supplied to the
    /// constructor. Adding, replacing, or removing routes does not modify the original dictionary.
    /// </para>
    /// <para>
    /// Route mutations are not thread-safe and must only be performed when no requests are in flight. Entries are
    /// validated only when selected, so unused entries with whitespace keys or <see langword="null"/> clients do not
    /// affect other routes.
    /// </para>
    /// <para>
    /// When <see cref="RoutePersistingRoutingChatClientOptions.OwnsInnerClients"/> is <see langword="true"/>, only clients
    /// still present in this dictionary when the routing client is disposed are disposed. Removing or replacing an
    /// entry does not dispose its previous client and transfers responsibility for that client's lifetime back to
    /// the caller.
    /// </para>
    /// </remarks>
    public IDictionary<string, IChatClient> Routes { get; }

    /// <summary>
    /// Gets the route that is currently active for the specified session.
    /// </summary>
    /// <param name="session">The session whose active route should be returned.</param>
    /// <returns>The key of the route that is currently active for the session.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> is <see langword="null"/>.</exception>
    public string GetActiveRoute(AgentSession session)
    {
        _ = Throw.IfNull(session);

        return this._sessionState.GetOrInitializeState(session).ActiveRoute ??
            this._defaultRoute ??
            throw new InvalidOperationException("No active or default route is available.");
    }

    /// <summary>
    /// Sets the route that is active for the specified session.
    /// </summary>
    /// <param name="session">The session whose active route should be updated.</param>
    /// <param name="route">The key of the route to make active. Must be one of the registered routes.</param>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="session"/> or <paramref name="route"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="route"/> is not a registered route.</exception>
    public void SetActiveRoute(AgentSession session, string route)
    {
        _ = Throw.IfNull(session);
        _ = Throw.IfNull(route);

        if (!this.Routes.TryGetValue(route, out var client) || client is null)
        {
            throw new ArgumentException($"'{route}' is not registered with a usable chat client.", nameof(route));
        }

        var state = this._sessionState.GetOrInitializeState(session);
        state.ActiveRoute = route;
        this._sessionState.SaveState(session, state);
    }

    /// <inheritdoc/>
    protected override ValueTask<IChatClient> SelectClientAsync(
        RoutingContext context,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(context);

        return new ValueTask<IChatClient>(this.GetActiveClient(GetRequiredSession()));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        object? service = base.GetService(serviceType, serviceKey);
        if (service is not null)
        {
            return service;
        }

        // Best effort: forward to the client of the session's active route when a run is in progress,
        // otherwise to the default route's client.
        var session = AIAgent.CurrentRunContext?.Session;
        string? route = session is not null
            ? this._sessionState.GetOrInitializeState(session).ActiveRoute ?? this._defaultRoute
            : this._defaultRoute;

        return route is not null &&
            this.Routes.TryGetValue(route, out var client) &&
            client is not null
                ? client.GetService(serviceType, serviceKey)
                : null;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing && Interlocked.Exchange(ref this._disposed, 1) == 0 && this._ownsInnerClients)
        {
            HashSet<IChatClient> disposedClients = new(ChatClientReferenceComparer.Instance);
            foreach (var client in this.Routes.Values)
            {
                if (client is not null && disposedClients.Add(client))
                {
                    client.Dispose();
                }
            }
        }

        base.Dispose(disposing);
    }

    /// <summary>
    /// Gets the session of the current agent run, throwing when no run context or session is available.
    /// </summary>
    /// <exception cref="InvalidOperationException">No run context or no session is available.</exception>
    private static AgentSession GetRequiredSession()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(RoutePersistingRoutingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        return runContext.Session
            ?? throw new InvalidOperationException(
                $"{nameof(RoutePersistingRoutingChatClient)} requires a session. " +
                "Ensure the agent has a resolved session before invoking the chat client.");
    }

    /// <summary>
    /// Gets the client registered for the session's active route.
    /// </summary>
    /// <exception cref="InvalidOperationException">The active route is not a registered route.</exception>
    private IChatClient GetActiveClient(AgentSession session)
    {
        string route = this.GetActiveRoute(session);
        return this.GetClient(route, "active");
    }

    /// <summary>
    /// Gets the client registered for a route.
    /// </summary>
    /// <exception cref="InvalidOperationException">The route is unavailable or has no usable client.</exception>
    private IChatClient GetClient(string? route, string routeKind)
    {
        return route is not null && this.Routes.TryGetValue(route, out var client) && client is not null
            ? client
            : throw new InvalidOperationException(
                route is null
                    ? $"No {routeKind} route is available."
                    : $"No usable chat client is registered for the {routeKind} route '{route}'.");
    }

    private sealed class ChatClientReferenceComparer : IEqualityComparer<IChatClient>
    {
        public static ChatClientReferenceComparer Instance { get; } = new();

        public bool Equals(IChatClient? x, IChatClient? y) => ReferenceEquals(x, y);

        public int GetHashCode(IChatClient obj) => RuntimeHelpers.GetHashCode(obj);
    }
}
