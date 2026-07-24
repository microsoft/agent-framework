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
/// An <see cref="IChatClient"/> that routes each request to one of several inner chat clients.
/// </summary>
/// <remarks>
/// <para>
/// This decorator holds
/// multiple named inner clients (destinations) and selects one per request. By default, requests are routed
/// to the session's currently active destination, which is stored in the session's
/// <see cref="AgentSessionStateBag"/> as a <see cref="RoutingState"/>. Use
/// <see cref="SetActiveDestinationKey"/> and <see cref="GetActiveDestinationKey"/> to switch or inspect the
/// active destination key for a session.
/// </para>
/// <para>
/// The default destination for a new session is produced by the optional <c>stateInitializer</c> constructor
/// argument. When it is not supplied, the first entry in the inner clients dictionary is used.
/// </para>
/// <para>
/// A custom router can be supplied via <see cref="RoutingChatClientOptions.Router"/> to select a destination
/// key per request. For each request, the destination is resolved in the following order:
/// <list type="number">
/// <item>The router (when configured) is invoked to produce a key; otherwise the session's active destination key is used.</item>
/// <item>When the key matches a registered inner client, that client is used.</item>
/// <item>
/// When the key does not match a registered inner client and a fallback factory is configured, a client is created on the fly
/// for that request. By default the created client is disposed after the request completes; set
/// <see cref="RoutingChatClientOptions.DisableFallbackChatClientDisposal"/> to keep it (for example, when the factory caches or
/// returns shared clients).</item>
/// <item>Otherwise an <see cref="InvalidOperationException"/> is thrown.</item>
/// </list>
/// An empty string is treated as an ordinary key (looked up, then routed to the fallback factory); only
/// <see langword="null"/> is routed directly to the fallback factory.
/// </para>
/// <para>
/// It is valid to construct the client with no inner clients by using the constructor that accepts only a
/// fallback factory, in which case every request is served by the fallback factory.
/// </para>
/// <para>
/// This client resolves the current agent and session from <see cref="AIAgent.CurrentRunContext"/>, which is
/// set automatically when an agent's run methods are called. It must therefore be invoked within an agent run
/// that has a resolved session; calling it outside of an agent run (or before a session is resolved) throws
/// <see cref="InvalidOperationException"/>.
/// </para>
/// <para>
/// Instances are thread-safe across different sessions. A single session must not be used concurrently: the
/// per-session active destination state assumes only one request per session is in flight at a time.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class RoutingChatClient : IChatClient
{
    private readonly IReadOnlyDictionary<string, IChatClient> _innerClients;
    private readonly Func<RoutingContext, CancellationToken, ValueTask<string?>>? _router;
    private readonly Func<string?, RoutingContext, CancellationToken, ValueTask<IChatClient>> _fallbackFactory;
    private readonly ProviderSessionState<RoutingState> _sessionState;
    private readonly bool _disableFallbackChatClientDisposal;

    /// <summary>
    /// Initializes a new instance of the <see cref="RoutingChatClient"/> class that routes to a fixed set of
    /// inner clients.
    /// </summary>
    /// <param name="innerClients">The inner clients to route to, keyed by destination name. Must be non-empty.</param>
    /// <param name="stateInitializer">
    /// An optional function that initializes the <see cref="RoutingState"/> for a new session. Use this to
    /// specify the default destination a new session is routed to. When <see langword="null"/>, the default
    /// initializer selects the first entry in <paramref name="innerClients"/>.
    /// </param>
    /// <param name="options">Optional settings that control routing behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="innerClients"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="innerClients"/> is empty or contains a <see langword="null"/> value.
    /// </exception>
    public RoutingChatClient(
        IReadOnlyDictionary<string, IChatClient> innerClients,
        Func<AgentSession?, RoutingState>? stateInitializer = null,
        RoutingChatClientOptions? options = null)
        : this(RequireNonEmpty(innerClients), s_noFallbackFactory, stateInitializer, options)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="RoutingChatClient"/> class that serves every request from a
    /// fallback factory (no fixed inner clients).
    /// </summary>
    /// <param name="fallbackFactory">
    /// An asynchronous factory used to construct an <see cref="IChatClient"/> on the fly for the routed key. It
    /// receives the routed key (which may be <see langword="null"/> for the default destination), the
    /// <see cref="RoutingContext"/>, and a <see cref="CancellationToken"/>, and returns the client to use. A new
    /// client is created for each request that routes to the factory and, by default, disposed after that request
    /// completes (see <see cref="RoutingChatClientOptions.DisableFallbackChatClientDisposal"/>).
    /// </param>
    /// <param name="stateInitializer">
    /// An optional function that initializes the <see cref="RoutingState"/> for a new session. When
    /// <see langword="null"/>, the default initializer sets the active destination to <see langword="null"/>.
    /// </param>
    /// <param name="options">Optional settings that control routing behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="fallbackFactory"/> is <see langword="null"/>.</exception>
    public RoutingChatClient(
        Func<string?, RoutingContext, CancellationToken, ValueTask<IChatClient>> fallbackFactory,
        Func<AgentSession?, RoutingState>? stateInitializer = null,
        RoutingChatClientOptions? options = null)
        : this(new Dictionary<string, IChatClient>(), Throw.IfNull(fallbackFactory), stateInitializer, options)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="RoutingChatClient"/> class that routes to a fixed set of
    /// inner clients and falls back to a factory for unregistered keys.
    /// </summary>
    /// <param name="innerClients">The inner clients to route to, keyed by destination name. Must be non-empty.</param>
    /// <param name="fallbackFactory">
    /// An asynchronous factory used to construct an <see cref="IChatClient"/> on the fly when the routed key is
    /// not one of the registered inner clients. It receives the routed key (which may be <see langword="null"/>
    /// for the default destination), the <see cref="RoutingContext"/>, and a <see cref="CancellationToken"/>, and
    /// returns the client to use. A new client is created for each request that routes to the factory and, by
    /// default, disposed after that request completes (see
    /// <see cref="RoutingChatClientOptions.DisableFallbackChatClientDisposal"/>).
    /// </param>
    /// <param name="stateInitializer">
    /// An optional function that initializes the <see cref="RoutingState"/> for a new session. Use this to
    /// specify the default destination a new session is routed to. When <see langword="null"/>, the default
    /// initializer selects the first entry in <paramref name="innerClients"/>.
    /// </param>
    /// <param name="options">Optional settings that control routing behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="innerClients"/> or <paramref name="fallbackFactory"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="innerClients"/> contains a <see langword="null"/> value.
    /// </exception>
    public RoutingChatClient(
        IReadOnlyDictionary<string, IChatClient> innerClients,
        Func<string?, RoutingContext, CancellationToken, ValueTask<IChatClient>> fallbackFactory,
        Func<AgentSession?, RoutingState>? stateInitializer = null,
        RoutingChatClientOptions? options = null)
    {
        Throw.IfNull(innerClients);
        Throw.IfNull(fallbackFactory);

        foreach (var pair in innerClients)
        {
            if (pair.Value is null)
            {
                throw new ArgumentException($"The inner client for key '{pair.Key}' is null.", nameof(innerClients));
            }
        }

        this._innerClients = innerClients;
        this._router = options?.Router;
        this._fallbackFactory = fallbackFactory;
        this._disableFallbackChatClientDisposal = options?.DisableFallbackChatClientDisposal ?? false;

        string? defaultDestination = innerClients.Keys.FirstOrDefault();
        string stateKey = options?.StateKey ?? this.GetType().Name;
        this._sessionState = new ProviderSessionState<RoutingState>(
            stateInitializer ?? (_ => new RoutingState { ActiveDestination = defaultDestination }),
            stateKey,
            AgentJsonUtilities.DefaultOptions);
    }

    /// <summary>
    /// A fallback factory used by the inner-clients-only constructor. It resolves no client (returns
    /// <see langword="null"/>), so an unresolved key results in an <see cref="InvalidOperationException"/> when the
    /// request is resolved.
    /// </summary>
    private static readonly Func<string?, RoutingContext, CancellationToken, ValueTask<IChatClient>> s_noFallbackFactory =
        (_, _, _) => default;

    /// <summary>
    /// Validates that <paramref name="innerClients"/> is non-null and non-empty, returning it for chaining.
    /// </summary>
    private static IReadOnlyDictionary<string, IChatClient> RequireNonEmpty(IReadOnlyDictionary<string, IChatClient> innerClients)
    {
        Throw.IfNull(innerClients);

        if (innerClients.Count == 0)
        {
            throw new ArgumentException("At least one inner client must be provided.", nameof(innerClients));
        }

        return innerClients;
    }

    /// <inheritdoc/>
    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        var (agent, session) = GetRequiredRunContext();
        var (client, disposeAfterUse) = await this.ResolveClientAsync(messages, options, agent, session, cancellationToken).ConfigureAwait(false);
        try
        {
            return await client.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            if (disposeAfterUse)
            {
                client.Dispose();
            }
        }
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        var (agent, session) = GetRequiredRunContext();
        var (client, disposeAfterUse) = await this.ResolveClientAsync(messages, options, agent, session, cancellationToken).ConfigureAwait(false);

        try
        {
            await foreach (var update in client.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
            {
                yield return update;
            }
        }
        finally
        {
            if (disposeAfterUse)
            {
                client.Dispose();
            }
        }
    }

    /// <summary>
    /// Gets the currently active destination key for the specified session.
    /// </summary>
    /// <param name="session">The session whose active destination key should be returned.</param>
    /// <returns>
    /// The active destination key for the session, or <see langword="null"/> when the request is routed directly
    /// to the fallback factory.
    /// </returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> is <see langword="null"/>.</exception>
    public string? GetActiveDestinationKey(AgentSession session)
    {
        Throw.IfNull(session);

        return this._sessionState.GetOrInitializeState(session).ActiveDestination;
    }

    /// <summary>
    /// Sets the active destination key for the specified session.
    /// </summary>
    /// <param name="session">The session whose active destination key should be updated.</param>
    /// <param name="destinationKey">
    /// The destination key to make active. May be any string (a registered inner client key or a key handled by
    /// the fallback factory), or <see langword="null"/> to route the request directly to the fallback factory
    /// (invoked with a <see langword="null"/> key), which throws if no fallback factory is configured.
    /// </param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> is <see langword="null"/>.</exception>
    public void SetActiveDestinationKey(AgentSession session, string? destinationKey)
    {
        Throw.IfNull(session);

        var state = this._sessionState.GetOrInitializeState(session);
        state.ActiveDestination = destinationKey;
        this._sessionState.SaveState(session, state);
    }

    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        Throw.IfNull(serviceType);

        if (serviceKey is null && serviceType.IsInstanceOfType(this))
        {
            return this;
        }

        return this.GetActiveClientForService()?.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        foreach (var client in this._innerClients.Values)
        {
            client.Dispose();
        }
    }

    /// <summary>
    /// Gets the current agent and session from the ambient run context, throwing if either is unavailable.
    /// </summary>
    /// <exception cref="InvalidOperationException">No run context or session is available.</exception>
    private static (AIAgent Agent, AgentSession Session) GetRequiredRunContext()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(RoutingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        var session = runContext.Session
            ?? throw new InvalidOperationException(
                $"{nameof(RoutingChatClient)} requires a session. " +
                "Ensure the agent has a resolved session before invoking the chat client.");

        return (runContext.Agent, session);
    }

    /// <summary>
    /// Resolves the inner client that <see cref="GetService"/> should forward to. This is a best-effort lookup:
    /// it uses the active destination of the current run's session when available, otherwise the first inner client.
    /// </summary>
    private IChatClient? GetActiveClientForService()
    {
        var session = AIAgent.CurrentRunContext?.Session;
        string? key = session is not null
            ? this._sessionState.GetOrInitializeState(session).ActiveDestination
            : null;

        if (key is not null && this._innerClients.TryGetValue(key, out var client))
        {
            return client;
        }

        return this._innerClients.Count > 0 ? this._innerClients.Values.First() : null;
    }

    /// <summary>
    /// Resolves the destination client for a request using the configured router and fallback factory.
    /// </summary>
    /// <returns>
    /// A tuple containing the resolved client and a flag indicating whether the caller should dispose it after the
    /// request completes. The flag is <see langword="true"/> only for clients created by the fallback factory when
    /// disposal is not disabled; registered inner clients are owned by this instance and disposed at teardown.
    /// </returns>
    private async ValueTask<(IChatClient Client, bool DisposeAfterUse)> ResolveClientAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, AIAgent agent, AgentSession session, CancellationToken cancellationToken)
    {
        var state = this._sessionState.GetOrInitializeState(session);

        var context = new RoutingContext(
            agent,
            session,
            messages as IReadOnlyList<ChatMessage> ?? messages.ToList(),
            options,
            this._innerClients,
            state.ActiveDestination);

        string? key = this._router is not null
            ? await this._router(context, cancellationToken).ConfigureAwait(false)
            : context.ActiveDestination;

        if (key is not null && this._innerClients.TryGetValue(key, out var client))
        {
            return (client, false);
        }

        var created = await this._fallbackFactory(key, context, cancellationToken).ConfigureAwait(false)
            ?? throw new InvalidOperationException($"No inner client is registered for destination '{key ?? "(null)"}' and no fallback client is available.");

        return (created, !this._disableFallbackChatClientDisposal);
    }
}
