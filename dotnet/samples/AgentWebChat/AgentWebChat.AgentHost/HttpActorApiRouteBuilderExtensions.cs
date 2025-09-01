// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.AgentHost;

internal static partial class HttpActorApiRouteBuilderExtensions
{
    private const string BasePath = "/actors/v1";

    public static void MapActors(this IEndpointRouteBuilder endpoints, IActorClient? actorClient = null, [StringSyntax("Route")] string? path = default)
    {
        path ??= BasePath;
        actorClient ??= endpoints.ServiceProvider.GetRequiredService<IActorClient>();

        var routeGroup = endpoints.MapGroup(path);

        // GET /actors/v1/{actorType}/{actorKey}/{messageId}
        routeGroup.MapGet(
            "/{actorType}/{actorKey}/{messageId}", async (
            string actorType,
            string actorKey,
            string messageId,
            [FromQuery] bool? blocking,
            [FromQuery] bool? streaming,
            HttpContext context,
            CancellationToken cancellationToken) =>
                await HttpActorProcessor.GetResponseAsync(
                    actorType,
                    actorKey,
                    messageId,
                    blocking: blocking,
                    streaming: streaming,
                    context,
                    actorClient,
                    cancellationToken))
            .WithName("GetActorResponse");

        // POST /actors/v1/{actorType}/{actorKey}/{messageId}
        routeGroup.MapPost(
            "/{actorType}/{actorKey}/{messageId}", async (
            string actorType,
            string actorKey,
            string messageId,
            [FromQuery] bool? blocking,
            [FromQuery] bool? streaming,
            [FromBody] ActorRequest request,
            CancellationToken cancellationToken) =>
                await HttpActorProcessor.SendRequestAsync(
                    actorType,
                    actorKey,
                    messageId,
                    blocking: blocking,
                    streaming: streaming,
                    request,
                    actorClient,
                    cancellationToken))
            .WithName("SendActorRequest");

        // POST /actors/v1/{actorType}/{actorKey}/{messageId}:cancel
        routeGroup.MapPost(
            "/{actorType}/{actorKey}/{messageId}:cancel", async (
            string actorType,
            string actorKey,
            string messageId,
            CancellationToken cancellationToken) =>
                await HttpActorProcessor.CancelRequestAsync(actorType, actorKey, messageId, actorClient, cancellationToken))
            .WithName("CancelActorRequest");
    }
}
