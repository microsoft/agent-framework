// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.AgentHost;

internal static class HttpActorProcessor
{
    public static async Task<IResult> GetResponseAsync(
        string actorType,
        string actorKey,
        string messageId,
        bool? blocking,
        bool? streaming,
        HttpContext context,
        IActorClient actorClient,
        CancellationToken cancellationToken)
    {
        var actorId = new ActorId(actorType, actorKey);

        var responseHandle = await actorClient.GetResponseAsync(actorId, messageId, cancellationToken);

        if (responseHandle.TryGetResponse(out var response))
        {
            return GetResult(response);
        }

        if (streaming is true)
        {
            return new ActorUpdateStreamingResult(responseHandle);
        }

        if (blocking is true)
        {
            response = await responseHandle.GetResponseAsync(cancellationToken);
            return GetResult(response);
        }

        return Results.Ok(new ActorResponse
        {
            ActorId = actorId,
            MessageId = messageId,
            Status = RequestStatus.Pending,
            Data = JsonSerializer.Deserialize<JsonElement>("{}"),
        });
    }

    public static async Task<IResult> SendRequestAsync(
        string actorType,
        string actorKey,
        string messageId,
        bool? blocking,
        bool? streaming,
        ActorRequest request,
        IActorClient actorClient,
        CancellationToken cancellationToken)
    {
        var responseHandle = await actorClient.SendRequestAsync(request, cancellationToken);
        if (responseHandle.TryGetResponse(out var response))
        {
            return GetResult(response);
        }

        if (streaming is true)
        {
            return new ActorUpdateStreamingResult(responseHandle);
        }

        if (blocking is true)
        {
            response = await responseHandle.GetResponseAsync(cancellationToken);
            return GetResult(response);
        }

        return Results.Accepted();
    }

    private static IResult GetResult(ActorResponse response)
    {
        if (response.Status == RequestStatus.NotFound)
        {
            return Results.NotFound();
        }

        return Results.Ok(response);
    }

    public static async Task<IResult> CancelRequestAsync(
        string actorType,
        string actorKey,
        string messageId,
        IActorClient actorClient,
        CancellationToken cancellationToken)
    {
        var actorId = new ActorId(actorType, actorKey);
        var responseHandle = await actorClient.GetResponseAsync(actorId, messageId, cancellationToken);

        if (responseHandle.TryGetResponse(out var response))
        {
            if (response.Status is RequestStatus.NotFound)
            {
                return Results.NotFound();
            }
            else if (response.Status is RequestStatus.Completed or RequestStatus.Failed)
            {
                return Results.Conflict("The request has already completed and cannot be cancelled.");
            }
        }

        await responseHandle.CancelAsync(cancellationToken);
        return Results.NoContent();
    }

    private sealed class ActorUpdateStreamingResult(
        ActorResponseHandle responseHandle) : IResult
    {
        public async Task ExecuteAsync(HttpContext httpContext)
        {
            var cancellationToken = httpContext.RequestAborted;
            var response = httpContext.Response;
            response.Headers.ContentType = "text/event-stream";
            response.Headers.CacheControl = "no-cache,no-store";
            response.Headers.Connection = "keep-alive";

            // Make sure we disable all response buffering for SSE.
            response.Headers.ContentEncoding = "identity";
            httpContext.Features.GetRequiredFeature<IHttpResponseBodyFeature>().DisableBuffering();
            await response.Body.FlushAsync(cancellationToken);

            var updateTypeInfo = AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ActorRequestUpdate));

            await foreach (var update in responseHandle.WatchUpdatesAsync(cancellationToken).ConfigureAwait(false))
            {
                var eventData = JsonSerializer.Serialize(update, updateTypeInfo);
                var eventText = $"data: {eventData}\n\n";

                await response.WriteAsync(eventText, cancellationToken);
                await response.Body.FlushAsync(cancellationToken);
            }
        }
    }
}
