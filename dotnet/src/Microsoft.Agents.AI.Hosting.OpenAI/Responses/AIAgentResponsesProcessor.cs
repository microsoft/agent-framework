// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Model;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Utils;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// OpenAI Responses processor associated with a specific <see cref="AIAgent"/>.
/// </summary>
internal sealed class AIAgentResponsesProcessor
{
    private readonly AIAgent _agent;

    public AIAgentResponsesProcessor(AIAgent agent)
    {
        this._agent = agent ?? throw new ArgumentNullException(nameof(agent));
    }

    public async Task<IResult> CreateModelResponseAsync(ResponseCreationOptions responseCreationOptions, CancellationToken cancellationToken)
    {
        var options = new OpenAIResponsesRunOptions();
        AgentThread? agentThread = null; // not supported to resolve from conversationId

        var inputItems = responseCreationOptions.GetInput();
        var chatMessages = inputItems.AsChatMessages();

        if (responseCreationOptions.GetStream())
        {
            return new OpenAIStreamingResponsesResult(this._agent, chatMessages);
        }

        var agentResponse = await this._agent.RunAsync(chatMessages, agentThread, options, cancellationToken).ConfigureAwait(false);
        return new OpenAIResponseResult(agentResponse);
    }

    private sealed class OpenAIResponseResult(AgentRunResponse agentResponse) : IResult
    {
        public async Task ExecuteAsync(HttpContext httpContext)
        {
            // note: OpenAI SDK types provide their own serialization implementation
            // so we cant simply return IResult wrap for the typed-object.
            // instead writing to the response body can be done.

            var cancellationToken = httpContext.RequestAborted;
            var response = httpContext.Response;

            var chatResponse = agentResponse.AsChatResponse();
            var openAIResponse = chatResponse.AsOpenAIResponse();
            var openAIResponseJsonModel = openAIResponse as IJsonModel<OpenAIResponse>;
            Debug.Assert(openAIResponseJsonModel is not null);

            var writer = new Utf8JsonWriter(response.BodyWriter, new JsonWriterOptions { SkipValidation = false });
            openAIResponseJsonModel.Write(writer, ModelReaderWriterOptions.Json);
            await writer.FlushAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    private sealed class OpenAIStreamingResponsesResult(AIAgent agent, IEnumerable<ChatMessage> chatMessages) : IResult
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
                    var jsonTypeInfo = OpenAIResponsesJsonUtilities.DefaultOptions.GetTypeInfo(sseItem.Data.GetType());
                    var json = JsonSerializer.SerializeToUtf8Bytes(sseItem.Data, jsonTypeInfo);
                    bufferWriter.Write(json);
                },
                cancellationToken);
        }

        private async IAsyncEnumerable<SseItem<StreamingResponseEventBase>> GetStreamingResponsesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var sequenceNumber = 1;
            var outputIndex = 1;
            AgentThread? agentThread = null;

            ResponseItem? lastResponseItem = null;
            OpenAIResponse? lastOpenAIResponse = null;

            await foreach (var update in agent.RunStreamingAsync(chatMessages, thread: agentThread, cancellationToken: cancellationToken).ConfigureAwait(false))
            {
                if (string.IsNullOrEmpty(update.ResponseId)
                    && string.IsNullOrEmpty(update.MessageId)
                    && update.Contents is not { Count: > 0 })
                {
                    continue;
                }

                if (sequenceNumber == 1)
                {
                    lastOpenAIResponse = update.AsChatResponse().AsOpenAIResponse();

                    var responseCreated = new StreamingCreatedResponse(sequenceNumber++)
                    {
                        Response = lastOpenAIResponse
                    };
                    yield return new(responseCreated, responseCreated.Type);
                }

                if (update.Contents is not { Count: > 0 })
                {
                    continue;
                }

                // to help convert the AIContent into OpenAI ResponseItem we pack it into the known "chatMessage"
                // and use existing convertion extension method
                var chatMessage = new ChatMessage(ChatRole.Assistant, update.Contents)
                {
                    MessageId = update.MessageId,
                    CreatedAt = update.CreatedAt,
                    RawRepresentation = update.RawRepresentation
                };

                foreach (var openAIResponseItem in MicrosoftExtensionsAIResponsesExtensions.AsOpenAIResponseItems([chatMessage]))
                {
                    if (chatMessage.MessageId is not null)
                    {
                        openAIResponseItem.SetId(chatMessage.MessageId);
                    }

                    lastResponseItem = openAIResponseItem;

                    var responseOutputItemAdded = new StreamingOutputItemAddedResponse(sequenceNumber++)
                    {
                        OutputIndex = outputIndex++,
                        Item = openAIResponseItem
                    };
                    yield return new(responseOutputItemAdded, responseOutputItemAdded.Type);
                }
            }

            if (lastResponseItem is not null)
            {
                // we were streaming "response.output_item.added" before
                // so we should complete it now via "response.output_item.done"
                var responseOutputDoneAdded = new StreamingOutputItemDoneResponse(sequenceNumber++)
                {
                    OutputIndex = outputIndex++,
                    Item = lastResponseItem
                };
                yield return new(responseOutputDoneAdded, responseOutputDoneAdded.Type);
            }

            if (lastOpenAIResponse is not null)
            {
                // complete the whole streaming with the full response model
                var responseCompleted = new StreamingCompletedResponse(sequenceNumber++)
                {
                    Response = lastOpenAIResponse
                };
                yield return new(responseCompleted, responseCompleted.Type);
            }
        }
    }
}
