// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

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
        Func<IEnumerable<ChatMessage>, AIAgent> agentFactory)
    {
        return endpoints.MapPost(pattern, async context =>
        {
            var cancellationToken = context.RequestAborted;

            RunAgentInput? input;
            try
            {
                input = await JsonSerializer.DeserializeAsync(context.Request.Body, AGUIJsonSerializerContext.Default.RunAgentInput, cancellationToken).ConfigureAwait(false);
            }
            catch (JsonException)
            {
                await TypedResults.BadRequest().ExecuteAsync(context).ConfigureAwait(false);
                return;
            }

            if (input is null)
            {
                await TypedResults.BadRequest().ExecuteAsync(context).ConfigureAwait(false);
                return;
            }

            var messages = input.Messages.AsChatMessages();
            var contextValues = input.Context;
            var forwardedProps = input.ForwardedProperties;
            var agent = agentFactory(messages);

            var events = agent.RunStreamingAsync(
                messages,
                cancellationToken: cancellationToken)
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    cancellationToken);

            var logger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            await new AGUIServerSentEventsResult(events, logger).ExecuteAsync(context).ConfigureAwait(false);
        });
    }
}
