// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
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
    /// Resolves a proxied AG-UI result from forwarded properties.
    /// </summary>
    /// <param name="forwardedProperties">The forwarded properties from the AG-UI request.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>
    /// A proxied result payload for <c>RUN_FINISHED.result</c>, or <see langword="null"/> to
    /// continue through the normal agent execution path.
    /// </returns>
    public delegate ValueTask<JsonElement?> ProxiedResultResolver(JsonElement forwardedProperties, CancellationToken cancellationToken);

    /// <summary>
    /// Maps an AG-UI agent endpoint.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        return MapAGUIInternal(endpoints, pattern, aiAgent, null);
    }

    /// <summary>
    /// Maps an AG-UI agent endpoint with optional proxied-result support.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance.</param>
    /// <param name="proxiedResultResolver">
    /// Optional delegate that resolves a proxied result from
    /// <see cref="RunAgentInput.ForwardedProperties"/> when forwarded properties are present.
    /// </param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent,
        ProxiedResultResolver proxiedResultResolver)
    {
        ArgumentNullException.ThrowIfNull(proxiedResultResolver);
        return MapAGUIInternal(endpoints, pattern, aiAgent, proxiedResultResolver);
    }

    private static RouteHandlerBuilder MapAGUIInternal(
        IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent,
        ProxiedResultResolver? proxiedResultResolver)
    {
        return endpoints.MapPost(pattern, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            var jsonOptions = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;

            if (proxiedResultResolver is not null && HasForwardedProperties(input.ForwardedProperties))
            {
                var proxiedResult = await proxiedResultResolver(input.ForwardedProperties, cancellationToken).ConfigureAwait(false);
                if (proxiedResult.HasValue)
                {
                    var proxiedEvents = StreamProxiedReadEventsAsync(input.ThreadId, input.RunId, proxiedResult.Value);
                    var proxiedLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
                    return new AGUIServerSentEventsResult(proxiedEvents, proxiedLogger);
                }
            }

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

            // Run the agent and convert to AG-UI events
            var events = aiAgent.RunStreamingAsync(
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

            var sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            return new AGUIServerSentEventsResult(events, sseLogger);
        });
    }

    private static async IAsyncEnumerable<BaseEvent> StreamProxiedReadEventsAsync(
        string threadId,
        string runId,
        JsonElement proxiedResult)
    {
        yield return new RunStartedEvent
        {
            ThreadId = threadId,
            RunId = runId,
        };

        yield return new RunFinishedEvent
        {
            ThreadId = threadId,
            RunId = runId,
            Result = proxiedResult,
        };

        await Task.CompletedTask.ConfigureAwait(false);
    }

    private static bool HasForwardedProperties(JsonElement forwardedProperties) =>
        forwardedProperties.ValueKind == JsonValueKind.Object &&
        forwardedProperties.EnumerateObject().MoveNext();
}
