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
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        IHostedAgentBuilder agentBuilder,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapAGUIServer(agentBuilder.Name, pattern);
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint using a named agent registered in dependency injection.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="agentName">The name of the keyed agent registration to resolve from dependency injection.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapAGUIServer(pattern, agent);
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
    /// </para>
    /// <para>
    /// <strong>Trust model.</strong> The AG-UI <c>RunAgentInput.ThreadId</c> arrives
    /// from the wire and is treated as a chain-resume identifier — <em>not</em> as an
    /// authorization token. The <see cref="AgentSessionStore"/> contract carries no
    /// principal/owner dimension, so when a persistent store is registered any caller
    /// who knows or guesses another caller's <c>ThreadId</c> can resume that other
    /// caller's persisted thread. Hosts that serve more than one user must compose a
    /// principal dimension into the lookup key. The recommended way is to wrap the
    /// keyed <see cref="AgentSessionStore"/> in
    /// <see cref="IsolationKeyScopedAgentSessionStore"/>, typically by calling
    /// <c>UseClaimsBasedSessionIsolation(...)</c> from
    /// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c> (or by registering a custom
    /// <see cref="SessionIsolationKeyProvider"/>) and registering the store via the
    /// <c>WithSessionStore(...)</c> / <c>WithInMemorySessionStore(...)</c> helpers on
    /// <see cref="IHostedAgentBuilder"/> so that the wrapper is applied. When no
    /// isolation provider is registered, behavior is unchanged — the bare
    /// <c>ThreadId</c> is used as the conversation identifier, which is appropriate
    /// for first-run / single-user / prototyping scenarios but unsafe for
    /// multi-user hosts.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUIServer(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(aiAgent);

        var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(aiAgent.Name);

        // Ensure that we have an IsolationKeyScopedAgentSessionStore registered.
        var isolationKeyProvider = endpoints.ServiceProvider.GetService<SessionIsolationKeyProvider>();
        if (agentSessionStore?.GetService<IsolationKeyScopedAgentSessionStore>() is null)
        {
            agentSessionStore ??= new NoopAgentSessionStore();
            agentSessionStore = new IsolationKeyScopedAgentSessionStore(agentSessionStore, isolationKeyProvider, new() { Strict = isolationKeyProvider != null });
        }

        var hostAgent = new AIHostAgent(aiAgent, agentSessionStore);

        return endpoints.MapPost(pattern, async (
            [FromBody] RunAgentInput? input,
            [FromServices] IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions> jsonOptions,
            HttpContext context,
            CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;
            var streamOptions = context.GetEndpoint()?.Metadata.GetMetadata<AGUIStreamOptions>()
                ?? context.RequestServices.GetService<IOptions<AGUIStreamOptions>>()?.Value;

            var ctx = input.ToChatRequestContext(jsonSerializerOptions, streamOptions);

            var threadId = string.IsNullOrWhiteSpace(ctx.Input.ThreadId) ? Guid.NewGuid().ToString("N") : ctx.Input.ThreadId;
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
