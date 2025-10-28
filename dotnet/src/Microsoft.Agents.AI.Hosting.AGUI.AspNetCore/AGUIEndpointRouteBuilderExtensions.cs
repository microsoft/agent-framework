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
        return endpoints.MapPost(pattern, requestDelegate: async context =>
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

            var events = agent.RunStreamingAsync(
                messages,
                cancellationToken: cancellationToken)
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    cancellationToken);

            await new AGUIServerSentEventsResult(events).ExecuteAsync(context).ConfigureAwait(false);
        });
    }
}
