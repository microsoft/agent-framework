// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.AgentHost;

internal static class InvocationHttpProcessor
{
    public static async Task<IResult> GetOrCreateInvocationAsync(
        string name,
        string sessionId,
        string requestId,
        bool? stream,
        AgentRunRequest runRequest,
        HttpContext context,
        ILogger<Program> logger,
        AgentProxyFactory agentProxyFactory,
        CancellationToken cancellationToken)
    {
        var agent = agentProxyFactory.Create(name);
        var messages = runRequest.Messages ?? [];
        if (stream == true)
        {
            return new AgentRunStreamingResult(sessionId, requestId, messages, logger, agent);
        }

        var thread = agent.GetThread(sessionId);
        var result = await agent.RunAsync(messages, thread: thread, cancellationToken: cancellationToken);
        return Results.Ok<AgentRunResponse>(result);
    }

    public static async Task<IResult> CancelInvocationAsync(
        string name,
        string sessionId,
        string requestId,
        HttpContext context,
        ILogger<Program> logger,
        IActorClient actorClient,
        CancellationToken cancellationToken)
    {
        var requestHandle = await actorClient.GetResponseAsync(new ActorId(name, sessionId), requestId, cancellationToken);
        if (requestHandle.TryGetResponse(out var response))
        {
            if (response.Status is RequestStatus.NotFound)
            {
                return Results.NotFound();
            }
            else if (response.Status is RequestStatus.Completed or RequestStatus.Failed)
            {
                return Results.Conflict("The invocation has already completed and cannot be cancelled.");
            }

            Debug.Assert(response.Status is RequestStatus.Pending);
        }

        await requestHandle.CancelAsync(cancellationToken);
        return Results.NoContent();
    }

    private sealed class AgentRunStreamingResult(
        string sessionId,
        string requestId,
        IReadOnlyCollection<ChatMessage> messages,
        ILogger<Program> logger,
        AgentProxy agent) : IResult
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

            try
            {
                var thread = agent.GetThread(sessionId);
                var updateTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
                await foreach (var update in agent.RunStreamingAsync(messages, thread, cancellationToken: cancellationToken).ConfigureAwait(false))
                {
                    var eventData = JsonSerializer.Serialize(update, updateTypeInfo);
                    var eventText = $"data: {eventData}\n\n";

                    await response.WriteAsync(eventText, cancellationToken);
                    await response.Body.FlushAsync(cancellationToken);
                }

                await response.WriteAsync("data: completed\n\n", cancellationToken);
                await response.Body.FlushAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                Log.SseStreamingCancelled(logger, requestId);
            }
            catch (Exception ex)
            {
                Log.SseStreamingError(logger, ex, requestId);
            }
        }
    }
}
