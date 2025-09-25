// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Actor;

[SuppressMessage("Performance", "CA1812")]
[SuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code", Justification = "<Pending>")]
[SuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.", Justification = "<Pending>")]
internal sealed class HttpActorProcessor
{
    private readonly IActorClient _actorClient;

    public HttpActorProcessor(IActorClient actorClient)
    {
        this._actorClient = actorClient;
    }

    public async Task<IResult> GetResponseAsync(
        string actorType,
        string actorKey,
        string messageId,
        bool? blocking,
        bool? streaming,
        CancellationToken cancellationToken)
    {
        var actorId = new ActorId(actorType, actorKey);
        var responseHandle = await this._actorClient.GetResponseAsync(actorId, messageId, cancellationToken).ConfigureAwait(false);
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
            response = await responseHandle.GetResponseAsync(cancellationToken).ConfigureAwait(false);
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

    public async Task<IResult> SendRequestAsync(
        string actorType,
        string actorKey,
        string messageId,
        bool? blocking,
        bool? streaming,
        SendMessageRequest sendMessageRequest,
        CancellationToken cancellationToken)
    {
        var actorId = new ActorId(actorType, actorKey);
        var request = new ActorRequest(actorId, messageId, sendMessageRequest.Method, sendMessageRequest.Params);

        var responseHandle = await this._actorClient.SendRequestAsync(request, cancellationToken).ConfigureAwait(false);
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
            response = await responseHandle.GetResponseAsync(cancellationToken).ConfigureAwait(false);
            return GetResult(response);
        }

        return Results.Accepted();
    }

    public async Task<IResult> CancelRequestAsync(
        string actorType,
        string actorKey,
        string messageId,
        CancellationToken cancellationToken)
    {
        var actorId = new ActorId(actorType, actorKey);
        var responseHandle = await this._actorClient.GetResponseAsync(actorId, messageId, cancellationToken).ConfigureAwait(false);

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

        await responseHandle.CancelAsync(cancellationToken).ConfigureAwait(false);
        return Results.NoContent();
    }

    private static IResult GetResult(ActorResponse response)
    {
        if (response.Status == RequestStatus.NotFound)
        {
            return Results.NotFound();
        }

        return Results.Ok(response);
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
            await response.Body.FlushAsync(cancellationToken).ConfigureAwait(false);

            var updateTypeInfo = AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ActorRequestUpdate));

            await foreach (var update in responseHandle.WatchUpdatesAsync(cancellationToken).ConfigureAwait(false))
            {
                var eventData = JsonSerializer.Serialize(update, updateTypeInfo);
                var eventText = $"data: {eventData}\n\n";

                await response.WriteAsync(eventText, cancellationToken).ConfigureAwait(false);
                await response.Body.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
        }
    }
}
