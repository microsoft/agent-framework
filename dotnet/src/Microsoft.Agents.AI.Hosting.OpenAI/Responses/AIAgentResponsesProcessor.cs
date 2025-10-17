// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common.Id;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation.Stream;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// OpenAI Responses processor for <see cref="AIAgent"/>.
/// </summary>
internal static class AIAgentResponsesProcessor
{
    public static async Task<IResult> CreateModelResponseAsync(AIAgent agent, CreateResponse request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(agent);

        // Create ID generator from the request
        var idGenerator = DefaultIdGenerator.From(request);

        // Create invocation context
        var context = new AgentInvocationContext(idGenerator, idGenerator.ResponseId, idGenerator.ConversationId);

        if (request.Stream == true)
        {
            return new StreamingResponse(agent, request, context);
        }

        try
        {
            var messages = request.Input.GetInputMessages().Select(i => i.ToChatMessage());
            var response = await agent.RunAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false);
            return Results.Ok(response.ToResponse(request, context));
        }
        catch (Exception e)
        {
            Activity.Current?.AddException(e);
            if (e is AgentInvocationException)
            {
                throw;
            }

            throw new AgentInvocationException(new ResponseError { Code = "server_error", Message = e.Message });
        }
    }

    private sealed class StreamingResponse(AIAgent agent, CreateResponse createResponse, AgentInvocationContext context) : IResult
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
                    using var writer = new Utf8JsonWriter(bufferWriter);
                    JsonSerializer.Serialize(writer, sseItem.Data, ResponsesJsonContext.Default.StreamingResponseEvent);
                    writer.Flush();
                },
                cancellationToken);
        }

        private async IAsyncEnumerable<SseItem<StreamingResponseEvent>> GetStreamingResponsesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var messages = createResponse.GetInputMessages(context.JsonSerializerOptions);
            var updates = agent.RunStreamingAsync(messages, cancellationToken: cancellationToken);
            IList<Action<ResponseUsage>> usageUpdaters = [];

            var seq = SequenceNumberFactory.Default;
            var outputGenerator = new AfItemResourceGenerator()
            {
                Context = context,
                NotifyOnUsageUpdate = usage =>
                {
                    foreach (var updater in usageUpdaters)
                    {
                        updater(usage);
                    }
                },
                Updates = updates,
                Seq = seq
            };

            var generator = new NestedResponseGenerator(
                seq,
                context.ResponseId,
                context.ConversationId,
                createResponse,
                outputGenerator,
                usageUpdaters.Add);

            await foreach (var group in generator.GenerateAsync(cancellationToken).ConfigureAwait(false))
            {
                await foreach (var e in group.Events
                                              .WithCancellation(cancellationToken)
                                              .ConfigureAwait(false))
                {
                    // Determine the event type string for SSE
                    var eventType = e.Type;
                    yield return new SseItem<StreamingResponseEvent>(e, eventType);
                }
            }
        }
    }
}
