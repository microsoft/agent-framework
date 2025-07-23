// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents.Runtime;

internal static class ActorFrameworkWebApplicationExtensions
{
    public static void MapAgents(this WebApplication app)
    {
        app.MapPost(
            "/invocations/actor/{name}/{sessionId}/{requestId}", async (
            string name,
            string sessionId,
            string requestId,
            [FromQuery] bool? stream,
            [FromBody] JsonElement request,
            HttpContext context,
            ILogger<Program> logger,
            IActorClient actorClient,
            CancellationToken cancellationToken) =>
            {
                var stopwatch = Stopwatch.StartNew();
                var streamRequested = stream == true;

                Log.ActorInvocationStarted(logger, name, sessionId, requestId, streamRequested);
                Log.ActorRequestReceived(logger, requestId, request.GetRawText().Length, streamRequested);

                try
                {
                    var responseHandle = await actorClient.SendRequestAsync(new ActorRequest(new ActorId(name, sessionId), requestId, method: "run", @params: request), cancellationToken);
                    Log.ActorRequestSent(logger, requestId, name, sessionId);

                    if (!responseHandle.TryGetResponse(out var response))
                    {
                        Log.ActorResponseHandleObtained(logger, requestId, false);

                        if (stream == true)
                        {
                            Log.SseStreamingStarted(logger, requestId);
                            // If no response is available and streaming is requested, stream the response handle.
                            var result = await StreamResponse(context, responseHandle, cancellationToken);
                            Log.ActorInvocationCompleted(logger, name, sessionId, requestId, RequestStatus.Pending, stopwatch.ElapsedMilliseconds);
                            return result;
                        }

                        // Otherwise, wait for a response to become available.
                        Log.WaitingForActorResponse(logger, requestId);
                        response = await responseHandle.GetResponseAsync(cancellationToken);
                    }
                    else
                    {
                        Log.ActorResponseHandleObtained(logger, requestId, true);
                    }

                    Log.ActorResponseReceived(logger, requestId, response.Status);
                    var processResult = await ProcessResponse(name, sessionId, requestId, stream, context, responseHandle, response, cancellationToken);
                    Log.ActorInvocationCompleted(logger, name, sessionId, requestId, response.Status, stopwatch.ElapsedMilliseconds);
                    return processResult;
                }
                catch (Exception ex)
                {
                    Log.ActorInvocationFailed(logger, ex, name, sessionId, requestId, stopwatch.ElapsedMilliseconds);
                    return Results.Problem("An error occurred processing the request.", statusCode: 500);
                }

                static async Task<IResult> StreamResponse(HttpContext context, ActorResponseHandle responseHandle, CancellationToken cancellationToken)
                {
                    var requestId = context.Request.RouteValues["requestId"]?.ToString() ?? "unknown";
                    var logger = context.RequestServices.GetRequiredService<ILogger<Program>>();

                    Log.SseStreamingStarted(logger, requestId);
                    InitializeSseResponse(context);
                    await context.Response.Body.FlushAsync(cancellationToken);

                    var updateCount = 0;
                    try
                    {
                        await foreach (var progress in responseHandle.WatchUpdatesAsync(cancellationToken))
                        {
                            // Properly serialize the progress data as JSON and escape for SSE
                            var progressJson = JsonSerializer.Serialize(progress.Data, (JsonSerializerOptions?)null);
                            var eventData = JsonSerializer.Serialize(new { @event = JsonDocument.Parse(progressJson).RootElement });
                            var eventText = $"data: {eventData}\n\n";

                            await context.Response.WriteAsync(eventText, cancellationToken);
                            await context.Response.Body.FlushAsync(cancellationToken);

                            updateCount++;
                            Log.SseProgressUpdateSent(logger, requestId, updateCount);
                        }

                        // Send completion marker
                        await context.Response.WriteAsync("data: completed\n\n", cancellationToken);
                        await context.Response.Body.FlushAsync(cancellationToken);

                        Log.SseStreamingCompleted(logger, requestId, updateCount);
                    }
                    catch (OperationCanceledException)
                    {
                        Log.SseStreamingCancelled(logger, requestId);
                    }
                    catch (Exception ex)
                    {
                        Log.SseStreamingError(logger, ex, requestId);
                    }

                    // TODO: refactor the enclosing method so we don't need to return a result here.
                    return Results.Empty;
                }

                static void InitializeSseResponse(HttpContext context)
                {
                    context.Response.Headers.ContentType = "text/event-stream";
                    context.Response.Headers.CacheControl = "no-cache,no-store";
                    context.Response.Headers.Connection = "keep-alive";

                    // Make sure we disable all response buffering for SSE.
                    context.Response.Headers.ContentEncoding = "identity";
                    context.Features.GetRequiredFeature<IHttpResponseBodyFeature>().DisableBuffering();
                }

                static async Task<IResult> ProcessResponse(
                string name,
                string sessionId,
                string requestId,
                bool? stream,
                HttpContext context,
                ActorResponseHandle responseHandle,
                ActorResponse response,
                CancellationToken cancellationToken)
                {
                    var logger = context.RequestServices.GetRequiredService<ILogger<Program>>();
                    var isStreaming = stream != false && response.Status == RequestStatus.Pending;

                    Log.ProcessingActorResponse(logger, requestId, response.Status, isStreaming);

                    var result = response.Status switch
                    {
                        // If the response is pending & streaming is disabled, return a 202 Accepted with the messageId.
                        RequestStatus.Pending when stream == false => Results.Accepted($"/invocations/actor/{name}/{sessionId}/{requestId}"),

                        // If streaming is not explicitly disabled, stream the response back.
                        RequestStatus.Pending => await StreamResponse(context, responseHandle, cancellationToken),
                        RequestStatus.Completed => Results.Ok(response.Data),

                        // If the response failed, we can return a 500 Internal Server Error.
                        RequestStatus.Failed => Results.Problem("The invocation failed.", statusCode: 500),
                        RequestStatus.NotFound => Results.NotFound(new { message = "Not found." }),// If the actor is not found, we can return a 404 Not Found.
                        _ => throw new NotSupportedException($"Unsupported request status: {response.Status}"),
                    };

                    var responseType = response.Status switch
                    {
                        RequestStatus.Pending when stream == false => "Accepted",
                        RequestStatus.Pending => "Streaming",
                        RequestStatus.Completed => "Ok",
                        RequestStatus.Failed => "Problem",
                        RequestStatus.NotFound => "NotFound",
                        _ => "Unknown"
                    };

                    Log.ActorResponseProcessed(logger, requestId, responseType);
                    return result;
                }
            })
        .WithName("Invocations");
    }
}
