// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;
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

        var chatMessages = request.Messages.Select(i => i.ToChatMessage());
        var chatClientAgentRunOptions = request.BuildOptions();

        if (request.Stream == true)
        {
            return new StreamingResponse(agent, request, chatMessages, chatClientAgentRunOptions);
        }

        var response = await agent.RunAsync(chatMessages, options: chatClientAgentRunOptions, cancellationToken: cancellationToken).ConfigureAwait(false);
        return Results.Ok(response.ToChatCompletion(request));
    }

    private sealed class StreamingResponse(
        AIAgent agent,
        CreateChatCompletion request,
        IEnumerable<ChatMessage> chatMessages,
        ChatClientAgentRunOptions? options) : IResult
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
            // The Unix timestamp (in seconds) of when the chat completion was created. Each chunk has the same timestamp.
            DateTimeOffset? createdAt = null;
            var chunkId = IdGenerator.NewId(prefix: "chatcmpl", delimiter: "-", stringLength: 13);

            await foreach (var agentRunResponseUpdate in agent.RunStreamingAsync(chatMessages, options: options, cancellationToken: cancellationToken).WithCancellation(cancellationToken))
            {
                var finishReason = (agentRunResponseUpdate.RawRepresentation is ChatResponseUpdate { FinishReason: not null } chatResponseUpdate)
                    ? chatResponseUpdate.FinishReason.ToString()
                    : "stop";

                var choiceChunks = new List<ChatCompletionChoiceChunk>();
                CompletionUsage? usageDetails = null;

                createdAt ??= agentRunResponseUpdate.CreatedAt;

                foreach (var content in agentRunResponseUpdate.Contents)
                {
                    // usage content is handled separately
                    if (content is UsageContent usageContent && usageContent.Details != null)
                    {
                        usageDetails = usageContent.Details.ToCompletionUsage();
                        continue;
                    }

                    ChatCompletionDelta? delta = content switch
                    {
                        TextContent textContent => new() { Content = textContent.Text },

                        // image
                        DataContent imageContent when imageContent.HasTopLevelMediaType("image") => new() { Content = imageContent.Base64Data.ToString() },
                        UriContent urlContent when urlContent.HasTopLevelMediaType("image") => new() { Content = urlContent.Uri.ToString() },

                        // audio
                        DataContent audioContent when audioContent.HasTopLevelMediaType("audio") => new() { Content = audioContent.Base64Data.ToString() },

                        // file
                        DataContent fileContent => new() { Content = fileContent.Base64Data.ToString() },
                        HostedFileContent fileContent => new() { Content = fileContent.FileId },

                        // function call
                        FunctionCallContent functionCallContent => new()
                        {
                            ToolCalls = [functionCallContent.ToChoiceMessageToolCall()]
                        },

                        // function result. ChatCompletions dont provide the results of function result per API reference
                        FunctionResultContent functionResultContent => null,

                        // ignore
                        _ => null
                    };

                    if (delta is null)
                    {
                        // unsupported but expected content type.
                        continue;
                    }

                    delta.Role = agentRunResponseUpdate.Role?.Value ?? "user";

                    var choiceChunk = new ChatCompletionChoiceChunk
                    {
                        Index = 0,
                        Delta = delta,
                        FinishReason = finishReason
                    };

                    choiceChunks.Add(choiceChunk);
                }

                var chunk = new ChatCompletionChunk
                {
                    Id = chunkId,
                    Created = (createdAt ?? DateTimeOffset.UtcNow).ToUnixTimeSeconds(),
                    Model = request.Model,
                    Choices = choiceChunks,
                    Usage = usageDetails
                };

                yield return new(chunk);
            }
        }
    }
}
