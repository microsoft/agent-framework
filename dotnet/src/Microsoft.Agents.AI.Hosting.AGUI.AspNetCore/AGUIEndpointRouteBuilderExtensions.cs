// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping AG-UI agents to ASP.NET Core endpoints.
/// </summary>
public static class MicrosoftAgentAIHostingAGUIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the AG-UI endpoints for.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder)
        => MapAGUI(endpoints, agentBuilder, path: null);

    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the AG-UI endpoints for.</param>
    /// <param name="path">Custom route path for the AG-UI endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, [StringSyntax("Route")] string? path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);

        AIAgent agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentBuilder.Name);
        return MapAGUI(endpoints, agent, path);
    }

    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given agent name.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agentName">The name of the agent to map the AG-UI endpoints for.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(this IEndpointRouteBuilder endpoints, string agentName)
        => MapAGUI(endpoints, agentName, path: null);

    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given agent name.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agentName">The name of the agent to map the AG-UI endpoints for.</param>
    /// <param name="path">Custom route path for the AG-UI endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(this IEndpointRouteBuilder endpoints, string agentName, [StringSyntax("Route")] string? path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);

        AIAgent agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return MapAGUI(endpoints, agent, path);
    }

    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the AG-UI endpoints for.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(this IEndpointRouteBuilder endpoints, AIAgent agent)
        => MapAGUI(endpoints, agent, path: null);

    /// <summary>
    /// Maps AG-UI endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the AG-UI endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the AG-UI endpoints for.</param>
    /// <param name="path">Custom route path for the AG-UI endpoint.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        AIAgent agent,
        [StringSyntax("Route")] string? path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent.Name));
        ValidateAgentName(agent.Name);

        path ??= $"/{agent.Name}/agui";

        return endpoints.MapPost(path, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

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
        });
    }

    private static void ValidateAgentName([NotNull] string agentName)
    {
        string escaped = Uri.EscapeDataString(agentName);
        if (!string.Equals(escaped, agentName, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"Agent name '{agentName}' contains characters invalid for URL routes.", nameof(agentName));
        }
    }
}
