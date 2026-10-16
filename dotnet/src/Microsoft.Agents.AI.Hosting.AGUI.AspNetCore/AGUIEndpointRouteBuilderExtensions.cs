// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Server;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
#if !NET10_0_OR_GREATER
using Microsoft.Extensions.Logging;
#endif
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides extension methods for mapping AG-UI agents to ASP.NET Core endpoints.
/// </summary>
/// <remarks>
/// The pipeline that converts <see cref="ChatResponseUpdate"/> streams into AG-UI events is provided by
/// the public AG-UI .NET SDK (<c>ChatResponseUpdateAGUIExtensions.AsAGUIEventStreamAsync</c>).
/// This class layers Agent Framework concerns (<see cref="AIHostAgent"/>, <see cref="AgentSessionStore"/>,
/// <see cref="IsolationKeyScopedAgentSessionStore"/>) on top of that pipeline.
/// </remarks>
public static class AGUIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps an AG-UI agent endpoint using an agent registered in dependency injection via <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="agentBuilder">The hosted agent builder that identifies the agent registration.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <remarks>
    /// <para>
    /// Singleton registrations are resolved once when the endpoint is mapped. Scoped and transient registrations are
    /// resolved for each request as described in <see cref="MapAGUIServer(IEndpointRouteBuilder, string, string)"/>.
    /// In both cases, the session store is resolved for each request and persisted sessions are partitioned by the
    /// registration name.
    /// </para>
    /// <para>
    /// See <see cref="MapAGUIServer(IEndpointRouteBuilder, string, AIAgent)"/> for authentication,
    /// authorization, and caller-scoped session isolation requirements.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        IHostedAgentBuilder agentBuilder,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);

        if (agentBuilder.Lifetime != ServiceLifetime.Singleton)
        {
            return endpoints.MapAGUIServer(agentBuilder.Name, pattern);
        }

        string agentName = agentBuilder.Name;
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return MapAGUIServerCore(endpoints, pattern, context =>
            CreateHostAgent(context.RequestServices, agent, agentName, sessionStorageIdentity: agentName));
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint using a named agent registered in dependency injection.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="agentName">The name of the keyed agent registration to resolve from dependency injection.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <remarks>
    /// <para>
    /// The keyed <see cref="AIAgent"/>, its keyed <see cref="AgentSessionStore"/>, and the
    /// <see cref="AgentIsolationKeyProvider"/> are resolved from <see cref="HttpContext.RequestServices"/>
    /// for each request, so the configured DI lifetime of the agent registration is honored.
    /// Persisted sessions are partitioned by <paramref name="agentName"/>, which remains stable across
    /// scoped or transient agent instances.
    /// </para>
    /// <para>
    /// See <see cref="MapAGUIServer(IEndpointRouteBuilder, string, AIAgent)"/> for authentication,
    /// authorization, and caller-scoped session isolation requirements.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);

        HostedAgentResolution.EnsureAgentRegistered(endpoints.ServiceProvider, agentName);

        return MapAGUIServerCore(endpoints, pattern, context =>
        {
            var agent = context.RequestServices.GetRequiredKeyedService<AIAgent>(agentName);
            return CreateHostAgent(context.RequestServices, agent, agentName, sessionStorageIdentity: agentName);
        });
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint that selects the agent to invoke for each request.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="agentSelector">
    /// A delegate invoked once per request that returns the agent to invoke, or <see langword="null"/> when
    /// no agent matches the request. The delegate can use route values, claims, headers, and
    /// <see cref="HttpContext.RequestServices"/> to select or resolve the agent.
    /// </param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <remarks>
    /// <para>
    /// When <paramref name="agentSelector"/> returns <see langword="null"/>, the endpoint responds with
    /// <c>404 Not Found</c> without loading session state.
    /// </para>
    /// <para>
    /// The selected agent's <see cref="AIAgent.Name"/> is its stable logical identity: it is used to resolve the
    /// keyed <see cref="AgentSessionStore"/> from <see cref="HttpContext.RequestServices"/> and to partition
    /// persisted sessions, so conversations continue across requests even when the selector returns a new agent
    /// instance each time. The selected agent must therefore have a non-empty name, and agents that must not
    /// share persisted sessions must have different names.
    /// </para>
    /// <para>
    /// Selection is not an authorization boundary. Enforce authorization with ASP.NET Core authorization
    /// policies, or return <see langword="null"/> from <paramref name="agentSelector"/> for agents the caller must
    /// not reach. See <see cref="MapAGUIServer(IEndpointRouteBuilder, string, AIAgent)"/> for authentication,
    /// authorization, and caller-scoped session isolation requirements.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        Func<HttpContext, AIAgent?> agentSelector)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentSelector);

        return MapAGUIServerCore(endpoints, pattern, context =>
        {
            if (agentSelector(context) is not { } agent)
            {
                return null;
            }

            string agentName = HostedAgentResolution.GetSelectedAgentName(agent);
            return CreateHostAgent(context.RequestServices, agent, agentName, sessionStorageIdentity: agentName);
        });
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <remarks>
    /// <para>
    /// If an <see cref="AgentSessionStore"/> is registered in dependency injection keyed by the agent's name,
    /// it will be used to persist conversation sessions across requests using the AG-UI thread ID as the
    /// conversation identifier. If no session store is registered, sessions are ephemeral (not persisted).
    /// The supplied agent instance is used for every request, while the session store is resolved from
    /// <see cref="HttpContext.RequestServices"/> for each request.
    /// </para>
    /// <para>
    /// <strong>Trust model.</strong> The AG-UI <c>RunAgentInput.ThreadId</c> arrives
    /// from the wire and is treated as a chain-resume identifier, not as an authorization
    /// token. Multi-user hosts must register an <see cref="AgentIsolationKeyProvider"/> that
    /// derives a stable, unique caller identity from trusted authentication, not from request
    /// fields such as <c>ThreadId</c>. For ASP.NET Core claims-based isolation, register
    /// <c>AddHttpContextAccessor()</c> and <c>UseClaimsBasedAgentIsolation(...)</c> from
    /// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c>.
    /// </para>
    /// <para>
    /// This method automatically wraps the keyed session store in
    /// <see cref="IsolationKeyScopedAgentSessionStore"/> unless that decorator is already present.
    /// The wrapper adds the caller's isolation partition to both session lookups and saves.
    /// When a provider is registered, the automatically added wrapper rejects missing or blank
    /// isolation keys instead of falling back to shared storage. Without a provider, that wrapper
    /// leaves keys unchanged: any caller who knows a thread ID can access that persisted session.
    /// This shared mode is unsafe for multi-user hosts. An existing isolation decorator retains
    /// its configured strictness.
    /// </para>
    /// <para>
    /// Isolation does not authenticate callers or authorize access to the agent or its tools.
    /// This method does not require authorization automatically. Configure ASP.NET Core
    /// authentication and authorization, and call <c>RequireAuthorization()</c> (or apply an
    /// appropriate policy) on the returned endpoint builder. Requiring authentication alone
    /// does not isolate persisted sessions; multi-user hosts need both controls. Clients must
    /// supply their credentials on every request, including continuation and approval requests.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(aiAgent);

        return MapAGUIServerCore(endpoints, pattern, context =>
            CreateHostAgent(context.RequestServices, aiAgent, aiAgent.Name, sessionStorageIdentity: null));
    }

    private static IEndpointConventionBuilder MapAGUIServerCore(
        IEndpointRouteBuilder endpoints,
        string pattern,
        Func<HttpContext, AIHostAgent?> hostAgentFactory)
    {
        IEndpointConventionBuilder endpoint = endpoints.MapPost(pattern, async (
            [FromBody] RunAgentInput? input,
            [FromServices] IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions> jsonOptions,
            HttpContext context,
            CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            // Resolve the agent before any session state is loaded so an unmatched selection never touches storage.
            if (hostAgentFactory(context) is not { } hostAgent)
            {
                return Results.NotFound();
            }

            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;
            var streamOptions = context.GetEndpoint()?.Metadata.GetMetadata<AGUIStreamOptions>()
                ?? context.RequestServices.GetService<IOptions<AGUIStreamOptions>>()?.Value;

            var ctx = input.ToChatRequestContext(jsonSerializerOptions, streamOptions);

            // AG-UI continuation is keyed by thread id. When the client does not supply one, generate a
            // stable id and write it back onto the input so the persisted session, the RUN_STARTED /
            // RUN_FINISHED events, and any continuation the client sends back all agree on the same id.
            var threadId = string.IsNullOrWhiteSpace(ctx.Input.ThreadId) ? Guid.NewGuid().ToString("N") : ctx.Input.ThreadId;
            ctx.Input.ThreadId = threadId;

            var session = await hostAgent.GetOrCreateSessionAsync(threadId, cancellationToken).ConfigureAwait(false);

            var events = hostAgent
                .RunStreamingAsync(
                    ctx.Messages,
                    session: session,
                    options: new ChatClientAgentRunOptions { ChatOptions = ctx.ChatOptions },
                    cancellationToken: cancellationToken)
                .AsChatResponseUpdatesAsync()
                .AsAGUIEventStreamAsync(ctx, cancellationToken);

            // Wrap the event stream to save the session after streaming completes.
            var eventsWithSessionSave = SaveSessionAfterStreamingAsync(events, hostAgent, threadId, session, cancellationToken);

#if NET10_0_OR_GREATER
            // On net10+ the framework provides first-class SSE result that flows through the
            // configured ASP.NET Core JsonSerializerOptions (which AddAGUIServer() augments with
            // AGUIJsonSerializerContext via the resolver chain).
            return TypedResults.ServerSentEvents(eventsWithSessionSave);
#else
            // On older TFMs we ship a small polyfill that emulates TypedResults.ServerSentEvents.
            var sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            return new AGUIServerSentEventsResult(eventsWithSessionSave, sseLogger);
#endif
        });

        MarkFeatureUsed();
        return endpoint;
    }

    private static AIHostAgent CreateHostAgent(
        IServiceProvider services,
        AIAgent agent,
        string? sessionStoreKey,
        string? sessionStorageIdentity)
    {
        var agentSessionStore = services.GetKeyedService<AgentSessionStore>(sessionStoreKey);

        // Ensure that we have an IsolationKeyScopedAgentSessionStore registered.
        var isolationKeyProvider = services.GetService<AgentIsolationKeyProvider>();
        if (agentSessionStore?.GetService<IsolationKeyScopedAgentSessionStore>() is null)
        {
            agentSessionStore ??= new NoopAgentSessionStore();
            agentSessionStore = new IsolationKeyScopedAgentSessionStore(agentSessionStore, isolationKeyProvider, new() { Strict = isolationKeyProvider != null });
        }

        return new AIHostAgent(agent, agentSessionStore, sessionStorageIdentity);
    }

    private static void MarkFeatureUsed()
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.HostingAGUI);
#pragma warning restore MAAI001
    }

    private static async IAsyncEnumerable<BaseEvent> SaveSessionAfterStreamingAsync(
        IAsyncEnumerable<BaseEvent> events,
        AIHostAgent hostAgent,
        string threadId,
        AgentSession session,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (BaseEvent evt in events.ConfigureAwait(false))
        {
            yield return evt;
        }

        await hostAgent.SaveSessionAsync(threadId, session, cancellationToken).ConfigureAwait(false);
    }
}
