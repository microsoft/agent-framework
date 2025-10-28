// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

internal static class AIAgentChatCompletionsProcessor
{
    public static async Task<IResult> CreateChatCompletionAsync(AIAgent agent, CreateChatCompletion request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(agent);

        if (request.Stream == true)
        {
            return new StreamingResponse(agent, request);
        }

        var messages = request.Messages.Select(i => i.ToChatMessage());
        var response = await agent.RunAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false);
        return Results.Ok(response.ToChatCompletion(request));
    }

#pragma warning disable CS9113 // Parameter is unread.
    private sealed class StreamingResponse(AIAgent agent, CreateChatCompletion request) : IResult
#pragma warning restore CS9113 // Parameter is unread.
    {
        public Task ExecuteAsync(HttpContext httpContext)
        {
#pragma warning disable IDE0059 // Unnecessary assignment of a value
            var cancellationToken = httpContext.RequestAborted;
#pragma warning restore IDE0059 // Unnecessary assignment of a value
            var response = httpContext.Response;

            // Set SSE headers
            response.Headers.ContentType = "text/event-stream";
            response.Headers.CacheControl = "no-cache,no-store";
            response.Headers.Connection = "keep-alive";
            response.Headers.ContentEncoding = "identity";
            httpContext.Features.GetRequiredFeature<IHttpResponseBodyFeature>().DisableBuffering();

            return Task.CompletedTask;

            //return SseFormatter.WriteAsync(
            //    source: this.GetStreamingResponsesAsync(cancellationToken),
            //    destination: response.Body,
            //    itemFormatter: (sseItem, bufferWriter) =>
            //    {
            //        var json = new BinaryData([1, 2, 3]);
            //        bufferWriter.Write(json);
            //    },
            //    cancellationToken);
        }

        //private async IAsyncEnumerable<SseItem<StreamingChatCompletionUpdate>> GetStreamingResponsesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        //{
        //    AgentThread? agentThread = null;

        //    var agentRunResponseUpdates = agent.RunStreamingAsync(chatMessages, thread: agentThread, cancellationToken: cancellationToken);
        //    var chatResponseUpdates = agentRunResponseUpdates.AsChatResponseUpdatesAsync();
        //    await foreach (var streamingChatCompletionUpdate in chatResponseUpdates.AsOpenAIStreamingChatCompletionUpdatesAsync(cancellationToken).ConfigureAwait(false))
        //    {
        //        yield return new SseItem<StreamingChatCompletionUpdate>(streamingChatCompletionUpdate);
        //    }
        //}
    }
}
