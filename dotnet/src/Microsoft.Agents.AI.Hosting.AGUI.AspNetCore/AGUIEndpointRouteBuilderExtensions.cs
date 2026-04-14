// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides extension methods for mapping AG-UI agents to ASP.NET Core endpoints.
/// </summary>
public static class AGUIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps an AG-UI agent endpoint using an agent registered in dependency injection via <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="agentBuilder">The hosted agent builder that identifies the agent registration.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        IHostedAgentBuilder agentBuilder,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapAGUI(agentBuilder.Name, pattern);
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint using a named agent registered in dependency injection.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="agentName">The name of the keyed agent registration to resolve from dependency injection.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapAGUI(pattern, agent);
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
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(aiAgent);

        var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(aiAgent.Name);
        var hostAgent = new AIHostAgent(aiAgent, agentSessionStore ?? new NoopAgentSessionStore());

        return endpoints.MapPost(pattern, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            var jsonOptions = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;

            var messages = input.Messages.AsChatMessages(jsonSerializerOptions);
            var clientTools = input.Tools?.AsAITools().ToList();

            // Create run options with AG-UI context in AdditionalProperties
            var runOptions = new ChatClientAgentRunOptions
            {
                ChatOptions = new ChatOptions
                {
                    Tools = clientTools,
                    AdditionalProperties = new AdditionalPropertiesDictionary
                    {
                        ["ag_ui_state"] = input.State,
                        ["ag_ui_context"] = input.Context?.Select(c => new KeyValuePair<string, string>(c.Description, c.Value)).ToArray(),
                        ["ag_ui_forwarded_properties"] = input.ForwardedProperties,
                        ["ag_ui_thread_id"] = input.ThreadId,
                        ["ag_ui_run_id"] = input.RunId
                    }
                }
            };

            var threadId = string.IsNullOrWhiteSpace(input.ThreadId) ? Guid.NewGuid().ToString("N") : input.ThreadId;
            var session = await hostAgent.GetOrCreateSessionAsync(threadId, cancellationToken).ConfigureAwait(false);

            // Run the agent and convert to AG-UI events
            var events = hostAgent.RunStreamingAsync(
                messages,
                session: session,
                options: runOptions,
                cancellationToken: cancellationToken)
                .AsChatResponseUpdatesAsync()
                .FilterServerToolsFromMixedToolInvocationsAsync(clientTools, cancellationToken)
                .AsAGUIEventStreamAsync(
                    threadId,
                    input.RunId,
                    jsonSerializerOptions,
                    cancellationToken);

            // Wrap the event stream to save the session after streaming completes
            var eventsWithSessionSave = SaveSessionAfterStreamingAsync(events, hostAgent, threadId, session, cancellationToken);

            var sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            return new AGUIServerSentEventsResult(eventsWithSessionSave, sseLogger);
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
