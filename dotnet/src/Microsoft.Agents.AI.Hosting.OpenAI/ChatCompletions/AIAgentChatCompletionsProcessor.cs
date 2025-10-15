// Copyright (c) Microsoft. All rights reserved.

using System.Buffers;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Utils;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

internal sealed class AIAgentChatCompletionsProcessor
{
    private readonly AIAgent _agent;

    public AIAgentChatCompletionsProcessor(AIAgent agent)
    {
        this._agent = agent;
    }

    public async Task<IResult> CreateChatCompletionAsync(ChatCompletionOptions chatCompletionOptions, CancellationToken cancellationToken)
    {
        AgentThread? agentThread = null; // not supported to resolve from conversationId

        var inputItems = chatCompletionOptions.GetMessages();
        var chatMessages = inputItems.AsChatMessages();

        if (chatCompletionOptions.GetStream())
        {
            return new OpenAIStreamingChatCompletionResult(this._agent, chatMessages);
        }

        var agentResponse = await this._agent.RunAsync(chatMessages, agentThread, cancellationToken: cancellationToken).ConfigureAwait(false);
        return new OpenAIChatCompletionResult(agentResponse);
    }

    private sealed class OpenAIChatCompletionResult(AgentRunResponse agentRunResponse) : IResult
    {
        public async Task ExecuteAsync(HttpContext httpContext)
        {
            // note: OpenAI SDK types provide their own serialization implementation
            // so we cant simply return IResult wrap for the typed-object.
            // instead writing to the response body can be done.

            var cancellationToken = httpContext.RequestAborted;
            var response = httpContext.Response;

            var chatResponse = agentRunResponse.AsChatResponse();
            var openAIChatCompletion = chatResponse.AsOpenAIChatCompletion();
            var openAIChatCompletionJsonModel = openAIChatCompletion as IJsonModel<ChatCompletion>;
            Debug.Assert(openAIChatCompletionJsonModel is not null);

            var writer = new Utf8JsonWriter(response.BodyWriter, new JsonWriterOptions { SkipValidation = false });
            openAIChatCompletionJsonModel.Write(writer, ModelReaderWriterOptions.Json);
            await writer.FlushAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    private sealed class OpenAIStreamingChatCompletionResult(AIAgent agent, IEnumerable<ChatMessage> chatMessages) : IResult
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
                source: this.GetStreamingResponsesAsync(cancellationToken),
                destination: response.Body,
                itemFormatter: (sseItem, bufferWriter) =>
                {
                    var sseDataJsonModel = (IJsonModel<StreamingChatCompletionUpdate>)sseItem.Data;
                    var json = sseDataJsonModel.Write(ModelReaderWriterOptions.Json);
                    bufferWriter.Write(json);
                },
                cancellationToken);
        }

        private async IAsyncEnumerable<SseItem<StreamingChatCompletionUpdate>> GetStreamingResponsesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            AgentThread? agentThread = null;

            var agentRunResponseUpdates = agent.RunStreamingAsync(chatMessages, thread: agentThread, cancellationToken: cancellationToken);
            var chatResponseUpdates = agentRunResponseUpdates.AsChatResponseUpdatesAsync();
            await foreach (var streamingChatCompletionUpdate in chatResponseUpdates.AsOpenAIStreamingChatCompletionUpdatesAsync(cancellationToken).ConfigureAwait(false))
            {
                yield return new SseItem<StreamingChatCompletionUpdate>(streamingChatCompletionUpdate);
            }
        }
    }
}
