// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.AgentHost;

internal static class ActorFrameworkWebApplicationExtensions
{
    public static void MapAgentInvocation(this IEndpointRouteBuilder endpoints, [StringSyntax("Route")] string path)
    {
        var routeGroup = endpoints.MapGroup(path);

        routeGroup.MapPost(
            "/agent/{name}/{sessionId}/{messageId}", async (
            string name,
            string sessionId,
            string messageId,
            [FromQuery] bool? stream,
            [FromBody] AgentRunRequest runRequest,
            HttpContext context,
            ILogger<Program> logger,
            AgentProxyFactory agentProxyFactory,
            CancellationToken cancellationToken) =>
                await InvocationHttpProcessor.GetOrCreateInvocationAsync(name, sessionId, messageId, stream, runRequest, context, logger, agentProxyFactory, cancellationToken))
            .WithName("GetOrCreateInvocation");

        routeGroup.MapPost(
            "/agent/{name}/{sessionId}/{messageId}:cancel", async (
            string name,
            string sessionId,
            string messageId,
            HttpContext context,
            ILogger<Program> logger,
            IActorClient actorClient,
            CancellationToken cancellationToken) =>
                await InvocationHttpProcessor.CancelInvocationAsync(name, sessionId, messageId, context, logger, actorClient, cancellationToken))
            .WithName("CancelInvocation");
    }

    public static void MapAgentDiscovery(this IEndpointRouteBuilder endpoints, [StringSyntax("Route")] string path)
    {
        var routeGroup = endpoints.MapGroup(path);
        routeGroup.MapGet("/", async (
            AgentCatalog agentCatalog,
            CancellationToken cancellationToken) =>
            {
                var results = new List<AgentDiscoveryCard>();
                await foreach (var result in agentCatalog.GetAgentsAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(new AgentDiscoveryCard
                    {
                        Name = result.Name!,
                        Description = result.Description,
                    });
                }

                return Results.Ok(results);
            })
            .WithName("GetAgents");
    }

    internal sealed class AgentDiscoveryCard
    {
        public required string Name { get; set; }

        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? Description { get; set; }
    }
}
