// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
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
    /// Maps an AG-UI agent endpoint using a static agent instance.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance to use for all requests.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="endpoints"/> or <paramref name="aiAgent"/> is <see langword="null"/>.
    /// </exception>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(aiAgent);

        return endpoints.MapAGUI(pattern, (_, _) => new ValueTask<AIAgent?>(aiAgent));
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint with dynamic agent resolution using a factory delegate.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">
    /// The URL pattern for the endpoint. May include route parameters (e.g., "/agents/{agentId}")
    /// that can be accessed via <c>HttpContext.GetRouteValue</c> in the factory.
    /// </param>
    /// <param name="agentFactory">
    /// A factory function that resolves an <see cref="AIAgent"/> based on the request context.
    /// The factory receives the <see cref="HttpContext"/> and a <see cref="CancellationToken"/>.
    /// Return <see langword="null"/> to produce a 404 Not Found response.
    /// </param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="endpoints"/> or <paramref name="agentFactory"/> is <see langword="null"/>.
    /// </exception>
    /// <remarks>
    /// <para>
    /// The factory function is invoked for each incoming request, allowing dynamic agent
    /// selection based on route parameters, headers, query strings, or other request context.
    /// </para>
    /// <para>
    /// The factory must be thread-safe as it may be invoked concurrently for multiple requests.
    /// </para>
    /// <example>
    /// <code>
    /// app.MapAGUI("/agents/{agentId}", async (context, cancellationToken) =>
    /// {
    ///     var agentId = context.GetRouteValue("agentId")?.ToString();
    ///     if (string.IsNullOrEmpty(agentId))
    ///         return null;
    ///
    ///     return await agentRepository.GetAgentByIdAsync(agentId, cancellationToken);
    /// });
    /// </code>
    /// </example>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        Func<HttpContext, CancellationToken, ValueTask<AIAgent?>> agentFactory)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentFactory);

        return endpoints.MapPost(pattern, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            AIAgent? agent;
            try
            {
                agent = await agentFactory(context, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                ILogger? logger = context.RequestServices.GetService<ILoggerFactory>()?.CreateLogger("Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.AgentResolution");
                logger?.LogError(ex, "Agent factory threw an exception during agent resolution");
                return Results.Problem(
                    title: "Agent Resolution Failed",
                    statusCode: StatusCodes.Status500InternalServerError);
            }

            if (agent is null)
            {
                return Results.NotFound();
            }

            return await ExecuteAgentAsync(agent, input, context, cancellationToken).ConfigureAwait(false);
        });
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint with dynamic agent resolution using a registered <see cref="IAGUIAgentResolver"/>.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">
    /// The URL pattern for the endpoint. May include route parameters (e.g., "/agents/{agentId}")
    /// that can be accessed via <c>HttpContext.GetRouteValue</c> in the resolver.
    /// </param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="endpoints"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// No <see cref="IAGUIAgentResolver"/> is registered in the service container.
    /// </exception>
    /// <remarks>
    /// <para>
    /// This overload requires an <see cref="IAGUIAgentResolver"/> to be registered in the
    /// dependency injection container via <see cref="IServiceCollection"/>.
    /// </para>
    /// <para>
    /// The resolver is retrieved from the request's service provider, allowing for
    /// scoped resolver implementations if needed.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern)
    {
        ArgumentNullException.ThrowIfNull(endpoints);

        return endpoints.MapAGUI(pattern, async (context, cancellationToken) =>
        {
            IAGUIAgentResolver resolver = context.RequestServices.GetRequiredService<IAGUIAgentResolver>();
            return await resolver.ResolveAgentAsync(context, cancellationToken).ConfigureAwait(false);
        });
    }

    private static async Task<IResult> ExecuteAgentAsync(
        AIAgent agent,
        RunAgentInput input,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions> jsonOptions = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
        System.Text.Json.JsonSerializerOptions jsonSerializerOptions = jsonOptions.Value.SerializerOptions;

        IEnumerable<ChatMessage> messages = input.Messages.AsChatMessages(jsonSerializerOptions);
        List<AITool>? clientTools = input.Tools?.AsAITools().ToList();

        // Create run options with AG-UI context in AdditionalProperties
        ChatClientAgentRunOptions runOptions = new()
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

        // Run the agent and convert to AG-UI events
        IAsyncEnumerable<BaseEvent> events = agent.RunStreamingAsync(
            messages,
            options: runOptions,
            cancellationToken: cancellationToken)
            .AsChatResponseUpdatesAsync()
            .FilterServerToolsFromMixedToolInvocationsAsync(clientTools, cancellationToken)
            .AsAGUIEventStreamAsync(
                input.ThreadId,
                input.RunId,
                jsonSerializerOptions,
                cancellationToken);

        ILogger<AGUIServerSentEventsResult> sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
        return new AGUIServerSentEventsResult(events, sseLogger);
    }
}
