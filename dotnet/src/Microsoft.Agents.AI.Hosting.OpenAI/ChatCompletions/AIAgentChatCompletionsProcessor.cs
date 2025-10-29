// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.AI;

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

        var chatMessages = request.Messages.Select(i => i.ToChatMessage());
        var response = await agent.RunAsync(chatMessages, cancellationToken: cancellationToken).ConfigureAwait(false);
        return Results.Ok(response.ToChatCompletion(request));
    }

    private sealed class StreamingResponse(AIAgent agent, CreateChatCompletion request) : IResult
    {
        public Task ExecuteAsync(HttpContext httpContext)
        {
            var cancellationToken = httpContext.RequestAborted;
            var response = httpContext.Response;

            // Set SSE headers
            response.Headers.ContentType = "text/event-stream";
            response.Headers.CacheControl = "no-cache,no-store";
            response.Headers.Connection = "keep-alive";
            response.Headers.ContentEncoding = "identity";
            httpContext.Features.GetRequiredFeature<IHttpResponseBodyFeature>().DisableBuffering();

            return SseFormatter.WriteAsync(
                source: this.GetStreamingChunksAsync(cancellationToken),
                destination: response.Body,
                itemFormatter: (sseItem, bufferWriter) =>
                {
                    using var writer = new Utf8JsonWriter(bufferWriter);
                    JsonSerializer.Serialize(writer, sseItem.Data, ChatCompletionsJsonContext.Default.ChatCompletionChunk);
                    writer.Flush();
                },
                cancellationToken);
        }

        private async IAsyncEnumerable<SseItem<ChatCompletionChunk>> GetStreamingChunksAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var chatMessages = request.Messages.Select(i => i.ToChatMessage());
            await foreach (var agentRunResponseUpdate in agent.RunStreamingAsync(chatMessages, cancellationToken: cancellationToken).WithCancellation(cancellationToken))
            {
                var choiceChunks = new List<ChatCompletionChoiceChunk>();
                foreach (var content in agentRunResponseUpdate.Contents)
                {
                    var delta = content switch
                    {
                        TextContent textContent => new ChatCompletionDelta { Content = textContent.Text },

                        _ => throw new InvalidOperationException($"Got unsupported content: {content.GetType()}")
                    };
                    delta.Role = agentRunResponseUpdate.Role?.Value ?? "user";

                    var choiceChunk = new ChatCompletionChoiceChunk
                    {
                        Index = 0,
                        Delta = delta
                    };

                    choiceChunks.Add(choiceChunk);
                }

                var chunk = new ChatCompletionChunk
                {
                    Id = Guid.NewGuid().ToString(),
                    Created = 1,
                    Model = request.Model,
                    Choices = choiceChunks
                };

                yield return new(chunk);
            }
        }
    }
}
