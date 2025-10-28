// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides extension methods for mapping AG-UI agents to ASP.NET Core endpoints.
/// </summary>
public static class AGUIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps an AG-UI agent endpoint.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="agentFactory">Factory function to create an agent instance.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUIAgent(
        this IEndpointRouteBuilder endpoints,
        string pattern,
        Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> agentFactory)
    {
        return endpoints.MapPost(pattern, new RequestDelegate(async (HttpContext context) =>
        {
            var cancellationToken = context.RequestAborted;
            var input = await JsonSerializer.DeserializeAsync(context.Request.Body, AGUIJsonSerializerContext.Default.RunAgentInput, cancellationToken).ConfigureAwait(false);
            if (input is null)
            {
                context.Response.StatusCode = StatusCodes.Status400BadRequest;
                return;
            }
            var messages = input.Messages.AsChatMessages();
            var contextValues = input.Context;
            var forwardedProps = input.ForwardedProperties;
            AIAgent agent = agentFactory(messages, [], contextValues, forwardedProps);

            IAsyncEnumerable<BaseEvent> events = CreateEventStreamAsync(agent, messages, [], contextValues, forwardedProps, cancellationToken);

            IAsyncEnumerable<SseItem<string>> sseStream = MapEventsToSseItemsAsync(events, cancellationToken);

            await new ServerSentEventsResult<string>(sseStream).ExecuteAsync(context).ConfigureAwait(false);
        }));
    }

    private static async IAsyncEnumerable<BaseEvent> CreateEventStreamAsync(
        AIAgent agent,
        IEnumerable<ChatMessage> messages,
        IEnumerable<AITool> tools,
        IEnumerable<KeyValuePair<string, string>> contextValues,
        JsonElement forwardedProps,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string threadId = Guid.NewGuid().ToString("N");
        string runId = Guid.NewGuid().ToString("N");

        yield return new RunStartedEvent
        {
            ThreadId = threadId,
            RunId = runId
        };

        string? currentMessageId = null;

        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, cancellationToken: cancellationToken).WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            if (update.MessageId != currentMessageId)
            {
                if (currentMessageId is not null)
                {
                    yield return new TextMessageEndEvent
                    {
                        MessageId = currentMessageId
                    };
                }

                currentMessageId = update.MessageId;

                if (currentMessageId is not null && update.Role.HasValue)
                {
                    yield return new TextMessageStartEvent
                    {
                        MessageId = currentMessageId,
                        Role = update.Role.Value.Value
                    };
                }
            }

            if (!string.IsNullOrEmpty(update.Text) && currentMessageId is not null)
            {
                yield return new TextMessageContentEvent
                {
                    MessageId = currentMessageId,
                    Delta = update.Text
                };
            }
        }

        if (currentMessageId is not null)
        {
            yield return new TextMessageEndEvent
            {
                MessageId = currentMessageId
            };
        }

        yield return new RunFinishedEvent
        {
            ThreadId = threadId,
            RunId = runId,
            Result = null
        };
    }

    private static async IAsyncEnumerable<SseItem<string>> MapEventsToSseItemsAsync(
        IAsyncEnumerable<BaseEvent> events,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (BaseEvent evt in events.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            string json = JsonSerializer.Serialize(evt, evt.GetType(), AGUIJsonSerializerContext.Default);
            yield return new SseItem<string>(json, evt.Type);
        }
    }
}
