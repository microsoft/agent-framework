// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Actor;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Provides extensions to enable agent discovery endpoints in a web application.
/// </summary>
[SuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code", Justification = "<Pending>")]
[SuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.", Justification = "<Pending>")]
public static class WebApplicationExtensions
{
    private const string AgentsBasePath = "/agents/v1";
    private const string ActorsBasePath = "/actors/v1";

    /// <summary>
    /// Enables the agent discovery endpoint at the specified path.
    /// </summary>
    public static void EnableDiscovery(this IEndpointRouteBuilder endpoints, [StringSyntax("Route")] string? agentsPath = default, [StringSyntax("Route")] string? actorsPath = default)
    {
        agentsPath ??= AgentsBasePath;
        var agentRouteGroup = endpoints.MapGroup(agentsPath);
        agentRouteGroup.MapAgentsDiscovery();

        actorsPath ??= ActorsBasePath;
        var actorRouteGroup = endpoints.MapGroup(actorsPath);
        actorRouteGroup.MapHttpActorProcessing();
    }

    private static void MapAgentsDiscovery(this IEndpointRouteBuilder routeGroup)
    {
        var agentDiscovery = routeGroup.ServiceProvider.GetService<AgentDiscoveryProvider>();
        if (agentDiscovery is null)
        {
            throw new ArgumentException($"At least one {typeof(AIAgent)} should be added to discovery via {nameof(AgentHostingBuilderExtensions.WithDiscovery)}");
        }

        routeGroup
            .MapGet("/", (CancellationToken cancellationToken) => agentDiscovery.GetAllAgents())
            .WithName("GetAgents");

        routeGroup
            .MapGet("/{agentName}", (string agentName, CancellationToken cancellationToken) =>
            {
                if (!agentDiscovery.TryGetAgent(agentName, out var agentMetadata))
                {
                    return Results.NotFound();
                }

                return Results.Ok(agentMetadata);
            })
            .WithName("GetAgent");
    }

    private static void MapHttpActorProcessing(this IEndpointRouteBuilder endpoints)
    {
        var httpActorProcessor = endpoints.ServiceProvider.GetRequiredService<HttpActorProcessor>();

        // GET /actors/v1/{actorType}/{actorKey}/{messageId}
        endpoints.MapGet(
            "/{actorType}/{actorKey}/{messageId}", (
            string actorType,
            string actorKey,
            string messageId,
            [FromQuery] bool? blocking,
            [FromQuery] bool? streaming,
            HttpActorProcessor httpActorProcessor,
            CancellationToken cancellationToken) =>
                httpActorProcessor.GetResponseAsync(actorType, actorKey, messageId, blocking, streaming, cancellationToken)
            )
            .WithName("GetActorResponse");

        // POST /actors/v1/{actorType}/{actorKey}/{messageId}
        endpoints.MapPost(
            "/{actorType}/{actorKey}/{messageId}", (
            string actorType,
            string actorKey,
            string messageId,
            [FromQuery] bool? blocking,
            [FromQuery] bool? streaming,
            [FromBody] SendMessageRequest request,
            HttpActorProcessor httpActorProcessor,
            CancellationToken cancellationToken) =>
                httpActorProcessor.SendRequestAsync(actorType, actorKey, messageId, blocking, streaming, request, cancellationToken)
            )
            .WithName("SendActorRequest");

        // POST /actors/v1/{actorType}/{actorKey}/{messageId}:cancel
        endpoints.MapPost(
            "/{actorType}/{actorKey}/{messageId}:cancel", (
            string actorType,
            string actorKey,
            string messageId,
            CancellationToken cancellationToken) =>
                httpActorProcessor.CancelRequestAsync(actorType, actorKey, messageId, cancellationToken)
            )
            .WithName("CancelActorRequest");
    }
}
